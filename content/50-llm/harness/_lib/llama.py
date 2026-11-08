"""llama-server раздела «LLM»: поднять с нужными слотами и бюджетом KV, остановить.

-np (слоты) — сколько запросов сервер генерирует одновременно; -c — общий
бюджет KV-кэша в токенах, делится поровну между слотами. Оба меняются только
перезапуском, поэтому каждый замер поднимает свой сервер (старт ~1 с).
"""
from __future__ import annotations

import contextlib
import os
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request

LIB_DIR = "/opt/llama"
SERVER = f"{LIB_DIR}/llama-server"
MODEL_PATH = "/opt/models/qwen05-q8.gguf"
MODEL = "q"
HEALTH_TIMEOUT_S = 30
# Больше токенов KV llama-server под ограничением памяти задания (2 ГБ) не стартует:
# -np 32 -c 32768 стартует, -c 65536 — нет (спека §7.2).
KV_BUDGET = 32768
STDERR_LINES = 40


def http_threads(slots: int) -> int:
    """Потоки HTTP: на каждый слот плюс запас на ожидающие соединения, не больше 64."""
    return min(slots + 16, 64)


class LlamaStartError(RuntimeError):
    """llama-server не поднялся: упал при старте или не ответил на /health."""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _tail(path: str) -> str:
    with open(path, errors="replace") as handle:
        return "".join(handle.readlines()[-STDERR_LINES:])


def _healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


@contextlib.contextmanager
def serve(*, slots: int, ctx_total: int, cpus: set[int], extra: list[str] | None = None):
    """URL поднятого llama-server; при выходе сервер останавливается."""
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    command = [SERVER, "-m", MODEL_PATH, "--alias", MODEL, "-t", str(len(cpus)),
               "-np", str(slots), "-c", str(ctx_total), "--host", "127.0.0.1", "--port", str(port),
               # Под ограничением памяти задания (RLIMIT_AS): кэш промптов не помещается,
               # а пул HTTP-потоков без предела падает на создании потока при очереди.
               "--cache-ram", "0", "--threads-http", str(http_threads(slots)),
               *(extra or [])]
    with tempfile.NamedTemporaryFile("w+", prefix="llama-", suffix=".log", delete=False, dir=".") as log:
        log_path = log.name
    with open(log_path, "w") as log:
        # Харнесс запускается с минимальным окружением: путь к .so сервера задаём сами.
        # MALLOC_ARENA_MAX: каждая арена malloc резервирует 64 МиБ адресов, и под RLIMIT_AS
        # задания потоки HTTP при очереди запросов переставали создаваться (спека §7.3).
        env = {**os.environ, "LD_LIBRARY_PATH": LIB_DIR, "MALLOC_ARENA_MAX": "2"}
        proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log, start_new_session=True, env=env,
                                preexec_fn=lambda: os.sched_setaffinity(0, cpus))
    try:
        deadline = time.monotonic() + HEALTH_TIMEOUT_S
        while not _healthy(url):
            if proc.poll() is not None:
                raise LlamaStartError(f"llama-server завершился с кодом {proc.returncode} при старте "
                                      f"(-np {slots} -c {ctx_total}):\n{_tail(log_path)}")
            if time.monotonic() > deadline:
                raise LlamaStartError(f"llama-server не ответил на /health за {HEALTH_TIMEOUT_S} с:\n"
                                      f"{_tail(log_path)}")
            time.sleep(0.1)
        yield url
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
        os.unlink(log_path)
