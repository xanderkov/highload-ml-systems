"""Сервис под нагрузкой: поднять uvicorn с приложением из файла и подать открытую нагрузку.

Генератор нагрузки — сырой asyncio HTTP/1.1 с keep-alive (спайк раздела: httpx
держит расписание только до ~800 RPS на одном CPU, сырой клиент — до ~4000).
Открытый цикл: запрос i запланирован на t0 + i / rps и уходит в срок, даже если
предыдущие ещё не отвечены; latency считается от запланированного момента, поэтому
очередь в сервисе видна в latency, а не прячется в замедлении клиента.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

HEALTH_TIMEOUT_S = 30
TERM_GRACE_S = 3
MAX_GENERATOR_LAG_MS = 5
STDERR_TAIL_BYTES = 4000
_INITIAL_CONNECTIONS = 10
_HERE = Path(__file__).resolve().parent


class ServiceStartError(RuntimeError):
    """Сервис не поднялся: упал при старте или не ответил на /health."""


class LoadGeneratorLagging(RuntimeError):
    """Генератор не успевал отправлять запросы по расписанию: замер нечестный."""

    def __init__(self, result: "LoadResult"):
        super().__init__(
            f"генератор нагрузки отстаёт от расписания: lag p99 {result.lag_ms_p99:.1f} мс "
            f"> {MAX_GENERATOR_LAG_MS} мс; снизьте RPS"
        )
        self.result = result


def split_cpus() -> tuple[set[int], set[int]]:
    """(CPU генератора, CPU сервиса): один логический CPU генератору, остальные сервису."""
    cpus = sorted(os.sched_getaffinity(0))
    if len(cpus) < 4:
        print(f"на машине {len(cpus)} логических CPU, задание требует ≥ 4 логических CPU", file=sys.stderr)
        sys.exit(3)
    return {cpus[0]}, set(cpus[1:])


class ServiceURL(str):
    """Базовый URL сервиса; .pids() — живые процессы его группы (мастер и воркеры)."""

    pgid: int

    def pids(self) -> list[int]:
        out = []
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            try:
                stat = Path(f"/proc/{name}/stat").read_text()
            except OSError:
                continue
            fields = stat.rsplit(")", 1)[1].split()
            if fields[0] != "Z" and int(fields[2]) == self.pgid:
                out.append(int(name))
        return sorted(out)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _tail(path: str) -> str:
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - STDERR_TAIL_BYTES))
        return f.read().decode(errors="replace")


# Без прокси из окружения: сервис локальный, http_proxy не должен перехватывать /health.
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# Привязка к CPU в самом дочернем процессе перед exec: preexec_fn небезопасен,
# если в родителе есть потоки (torch), а этот обёрточный интерпретатор однопоточен.
_PIN_AND_EXEC = "import os, sys; os.sched_setaffinity(0, {int(c) for c in sys.argv[1].split(',')}); os.execv(sys.argv[2], sys.argv[2:])"


def _healthy(url: str) -> bool:
    try:
        with _DIRECT.open(url + "/health", timeout=1) as r:
            return r.status == 200
    except OSError:
        return False


def _stop_group(proc: subprocess.Popen) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=TERM_GRACE_S)
    except subprocess.TimeoutExpired:
        pass
    # Добиваем всю группу: воркеры, пережившие мастера, тоже в ней.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()


@contextlib.contextmanager
def start_service(app_path: str, *, workers: int = 1, torch_threads: int | None = None,
                  cpus: set[int], env: dict | None = None):
    """Поднимает `uvicorn <файл>:app` на свободном порту, привязанным к cpus; отдаёт базовый URL.

    Приложение импортирует соседние модули _lib (tinymodel и т. п.): они в PYTHONPATH.
    torch_threads передаётся как OMP_NUM_THREADS/MKL_NUM_THREADS и SERVICE_TORCH_THREADS.
    """
    app = Path(app_path).resolve()
    port = _free_port()
    url = ServiceURL(f"http://127.0.0.1:{port}")
    child_env = dict(os.environ)
    child_env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(_HERE), child_env.get("PYTHONPATH", "")) if p)
    if torch_threads is not None:
        for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "SERVICE_TORCH_THREADS"):
            child_env[name] = str(torch_threads)
    if env:
        child_env.update(env)
    cpu_list = ",".join(str(c) for c in sorted(cpus))
    cmd = [sys.executable, "-c", _PIN_AND_EXEC, cpu_list, sys.executable, "-m", "uvicorn", f"{app.stem}:app", "--app-dir", str(app.parent),
           "--host", "127.0.0.1", "--port", str(port), "--workers", str(workers),
           "--log-level", "warning", "--no-access-log"]
    with tempfile.NamedTemporaryFile(prefix="service-stderr-", delete=False) as log:
        log_path = log.name
    try:
        with open(log_path, "wb") as log:
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=child_env,
                                    start_new_session=True)
        url.pgid = proc.pid
        try:
            deadline = time.monotonic() + HEALTH_TIMEOUT_S
            while not _healthy(url):
                if proc.poll() is not None:
                    raise ServiceStartError(
                        f"сервис {app.name} завершился при старте (код {proc.returncode}):\n{_tail(log_path)}")
                if time.monotonic() > deadline:
                    raise ServiceStartError(
                        f"сервис {app.name} не ответил на /health за {HEALTH_TIMEOUT_S} с:\n{_tail(log_path)}")
                time.sleep(0.05)
            yield url
        finally:
            _stop_group(proc)
    finally:
        os.unlink(log_path)


@dataclass
class LoadResult:
    latencies_ms: list[float]  # только успешные ответы, от запланированного момента
    errors: int
    duration_s: float  # от t0 до последнего ответа (не меньше запланированной длительности)
    lag_ms_p99: float  # отставание фактической отправки от плана
    responses: list = field(default_factory=list)  # тело ответа по индексу запроса, None при ошибке

    def _pct(self, q: float) -> float:
        return float(np.percentile(self.latencies_ms, q)) if self.latencies_ms else float("nan")

    def p50(self) -> float:
        return self._pct(50)

    def p99(self) -> float:
        return self._pct(99)

    def throughput(self) -> float:
        """Успешных ответов в секунду."""
        return len(self.latencies_ms) / self.duration_s

    def goodput(self, slo_ms: float) -> float:
        """Успешных ответов в секунду, уложившихся в SLO."""
        return sum(1 for x in self.latencies_ms if x <= slo_ms) / self.duration_s


async def _read_response(reader: asyncio.StreamReader) -> tuple[int, bytes, bool]:
    """(статус, тело, можно ли переиспользовать соединение)."""
    head = await reader.readuntil(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    status = int(lines[0].split()[1])
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip().lower()
    if headers.get("transfer-encoding") == "chunked":
        parts = []
        while True:
            size = int((await reader.readuntil(b"\r\n")).split(b";")[0], 16)
            if size == 0:
                await reader.readuntil(b"\r\n")  # без трейлеров
                break
            parts.append(await reader.readexactly(size))
            await reader.readexactly(2)
        body = b"".join(parts)
    else:
        body = await reader.readexactly(int(headers.get("content-length", "0")))
    return status, body, headers.get("connection") != "close"


async def _run(host: str, port: int, path: str, rps: float, duration_s: float,
               make_body: Callable[[int], bytes], content_type: str, timeout_s: float):
    n = int(rps * duration_s)
    head = (f"POST {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
            f"Content-Type: {content_type}\r\nContent-Length: ").encode()
    free: list = []
    for _ in range(min(_INITIAL_CONNECTIONS, max(n, 1))):
        free.append(await asyncio.open_connection(host, port))

    lags = [0.0] * n
    done_at = [0.0] * n
    responses: list = [None] * n

    async def send(conn, i: int, due: float, request: bytes):
        reader, writer = conn
        writer.write(request)
        return await _read_response(reader)

    async def exchange(i: int, due: float, body: bytes):
        request = head + str(len(body)).encode() + b"\r\n\r\n" + body
        pooled = bool(free)
        conn = free.pop() if pooled else await asyncio.open_connection(host, port)
        try:
            status, data, reusable = await send(conn, i, due, request)
        except (ConnectionError, asyncio.IncompleteReadError):
            conn[1].close()
            if not pooled:
                raise
            # Сервер мог закрыть простаивавшее keep-alive соединение: одна попытка на новом.
            conn = await asyncio.open_connection(host, port)
            try:
                status, data, reusable = await send(conn, i, due, request)
            except BaseException:
                conn[1].close()
                raise
        except BaseException:
            conn[1].close()
            raise
        if reusable:
            free.append(conn)
        else:
            conn[1].close()
        return data if status == 200 else None

    async def fire(i: int, due: float):
        body = make_body(i)
        # Lag — только собственная задержка генератора (планирование + make_body). Ожидание
        # соединения сюда не входит: если сервис перегружен и не принимает соединения,
        # это его latency/ошибки, а не вина генератора.
        lags[i] = time.perf_counter() - due
        try:
            responses[i] = await asyncio.wait_for(exchange(i, due, body), timeout_s)
        except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, ValueError, IndexError):
            responses[i] = None
        done_at[i] = time.perf_counter() - due

    loop = asyncio.get_running_loop()
    tasks = []
    t0 = time.perf_counter() + 0.05
    for i in range(n):
        due = t0 + i / rps
        while True:
            d = due - time.perf_counter()
            if d <= 0:
                break
            await asyncio.sleep(d - 0.0015 if d > 0.002 else 0)
        tasks.append(loop.create_task(fire(i, due)))
    await asyncio.gather(*tasks)
    end = time.perf_counter()
    for _, writer in free:
        writer.close()
    return t0, end, lags, done_at, responses


def run_load(url: str, *, path: str = "/predict", rps: float, duration_s: float,
             make_body: Callable[[int], bytes], content_type: str, cpus: set[int],
             timeout_s: float = 10) -> LoadResult:
    """Открытая нагрузка: rps * duration_s POST-запросов по расписанию t0 + i / rps.

    Генератор работает в вызывающем потоке, на время замера привязанном к cpus.
    make_body(i) вызывается в момент отправки — он должен быть дешёвым (заготовьте тела заранее):
    lag = момент, когда тело готово, − план (планирование + make_body); ожидание соединения
    и ответа — это latency сервиса, а не lag генератора.
    Бросает LoadGeneratorLagging, если p99 отставания отправки от плана > 5 мс.
    """
    host_port = url.split("://", 1)[1].rstrip("/")
    host, port = host_port.rsplit(":", 1)
    old = os.sched_getaffinity(0)
    os.sched_setaffinity(0, set(cpus))
    try:
        t0, end, lags, done_at, responses = asyncio.run(
            _run(host, int(port), path, rps, duration_s, make_body, content_type, timeout_s))
    finally:
        os.sched_setaffinity(0, old)
    latencies = [done_at[i] * 1e3 for i, r in enumerate(responses) if r is not None]
    result = LoadResult(
        latencies_ms=latencies,
        errors=sum(1 for r in responses if r is None),
        duration_s=max(duration_s, end - t0),
        lag_ms_p99=float(np.percentile(lags, 99)) * 1e3 if lags else 0.0,
        responses=responses,
    )
    if result.lag_ms_p99 > MAX_GENERATOR_LAG_MS:
        raise LoadGeneratorLagging(result)
    return result


def cpu_seconds(pids: list[int]) -> float:
    """Сумма utime + stime процессов (с); исчезнувшие процессы пропускаются."""
    tick = os.sysconf("SC_CLK_TCK")
    total = 0
    for pid in pids:
        try:
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        except OSError:
            continue
        total += int(fields[11]) + int(fields[12])  # поля 14 и 15 в нумерации proc(5)
    return total / tick
