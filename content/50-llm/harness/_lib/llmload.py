"""Открытая нагрузка на генерацию текста: свой движок в отдельном процессе или HTTP-сервер.

Открытый цикл: запрос i уходит в t0 + i / rps, даже если прошлые ещё
генерируются. Время до первого токена (TTFT), межтокенное время и e2e
считаются от момента отправки по расписанию.

Свой движок — функция engine(model, inbox, max_batch) студента — крутится в
отдельном процессе на CPU сервиса; генератор и приём токенов — в этом
процессе на CPU генератора. Запросы идут движку через multiprocessing.Queue,
токены обратно — тоже; время токена — момент, когда его получил генератор.

HTTP — OpenAI-совместимый /v1/completions со stream: true (llama.cpp, vLLM).
"""
from __future__ import annotations

import asyncio
import contextlib
import gc
import json
import multiprocessing as mp
import os
import queue
import random
import threading
import time
import traceback
from dataclasses import dataclass, field

STALL_S = 10
MAX_LAG_S = 0.05
DRAIN_S = 120  # сколько ждать окончания генерации после последней отправки
_READY_TIMEOUT_S = 60


class LoadGeneratorLagging(RuntimeError):
    """Генератор не успевал отправлять запросы по расписанию: замер нечестный."""


class EngineStalled(RuntimeError):
    def __init__(self, message: str, pid: int):
        super().__init__(message)
        self.pid = pid


class EngineCrashed(RuntimeError):
    pass


# --- запросы и результат -----------------------------------------------------------

@dataclass
class Mix:
    """Смесь запросов: доля long_frac длинных ответов, остальные короткие."""
    short: int = 16
    long: int = 128
    long_frac: float = 0.2
    prompt_len: int = 16
    seed: int = 1
    vocab: int = 4096

    def requests(self, n: int) -> list[tuple[str, list[int], int]]:
        """[(класс, промпт-токены, max_new)] — одинаковые при одном seed."""
        rng = random.Random(self.seed)
        out = []
        for _ in range(n):
            is_long = rng.random() < self.long_frac
            prompt = [rng.randrange(self.vocab) for _ in range(self.prompt_len)]
            out.append(("long" if is_long else "short", prompt, self.long if is_long else self.short))
        return out


def prompt_text(prompt: list[int]) -> str:
    """Текстовый промпт для HTTP-сервера из тех же «токенов»."""
    return "Continue the list: " + " ".join(str(t) for t in prompt[:4])


@dataclass
class Rec:
    cls: str
    prompt: list[int]
    max_new: int
    ttft_s: float | None
    e2e_s: float | None
    tokens: list[int] | None
    n_tokens: int
    itl_s: list[float]
    error: str | None = None

    @property
    def full(self) -> bool:
        return self.error is None and self.n_tokens >= self.max_new


def _pct(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    values = sorted(values)
    return values[min(len(values) - 1, int(q / 100 * len(values)))]


@dataclass
class Result:
    per_request: list[Rec]
    duration_s: float
    wall_s: float = 0.0

    def _ok(self, cls: str | None) -> list[Rec]:
        return [r for r in self.per_request if r.error is None and (cls is None or r.cls == cls)]

    def ttft(self, cls: str | None, q: float) -> float:
        return _pct([r.ttft_s for r in self._ok(cls) if r.ttft_s is not None], q)

    def e2e(self, cls: str | None, q: float) -> float:
        return _pct([r.e2e_s for r in self._ok(cls) if r.e2e_s is not None], q)

    def itl(self, q: float) -> float:
        return _pct([x for r in self._ok(None) for x in r.itl_s], q)

    def tok_per_s(self) -> float:
        tokens = sum(r.n_tokens for r in self.per_request if r.error is None)
        return tokens / self.wall_s if self.wall_s else float("nan")

    def goodput(self, ttft_slo_s: float) -> float:
        good = [r for r in self.per_request if r.full and r.ttft_s is not None and r.ttft_s <= ttft_slo_s]
        return len(good) / self.duration_s

    def truncated(self) -> int:
        return sum(1 for r in self.per_request if r.error is None and r.n_tokens < r.max_new)

    def errors(self) -> int:
        return sum(1 for r in self.per_request if r.error is not None)

    def first_error(self) -> str | None:
        return next((r.error for r in self.per_request if r.error), None)


def _once_with_retry(run):
    """gc выключен на время прогона; при отставании генератора — один повтор."""
    for attempt in (1, 2):
        gc.collect()
        gc.disable()
        try:
            return run()
        except LoadGeneratorLagging:
            if attempt == 2:
                raise
        finally:
            gc.enable()


@contextlib.contextmanager
def _pinned(cpu: int):
    """Генератор — на своём CPU на время прогона; потом прежняя привязка."""
    before = os.sched_getaffinity(0)
    os.sched_setaffinity(0, {cpu})
    try:
        yield
    finally:
        os.sched_setaffinity(0, before)


# --- свой движок в отдельном процессе ------------------------------------------------

class Request:
    """Запрос в процессе движка: prompt, max_new; send(token) отдаёт токен клиенту."""

    def __init__(self, rid: int, prompt: list[int], max_new: int, out: mp.Queue):
        self.id = rid
        self.prompt = prompt
        self.max_new = max_new
        self.sent = 0
        self._out = out

    @property
    def done(self) -> bool:
        return self.sent >= self.max_new

    def send(self, token: int) -> None:
        if self.done:
            raise ValueError(f"запрос {self.id} уже получил все {self.max_new} токенов — "
                             "уберите закончившиеся запросы из батча")
        self.sent += 1
        self._out.put(("tok", self.id, int(token)))

    def __repr__(self) -> str:
        return f"Request(id={self.id}, prompt_len={len(self.prompt)}, max_new={self.max_new}, sent={self.sent})"


class Inbox:
    """Входящие запросы движка. poll() не ждёт; wait() ждёт запрос или закрытие."""

    def __init__(self, inq: mp.Queue, out: mp.Queue):
        self._in = inq
        self._out = out
        self._buffer: list[Request] = []
        self._closed = False

    def _take(self, block: bool) -> bool:
        try:
            item = self._in.get(block=block)
        except queue.Empty:
            return False
        if item is None:
            self._closed = True
        else:
            self._buffer.append(Request(*item, self._out))
        return True

    @property
    def closed(self) -> bool:
        """True, когда новых запросов больше не будет и все пришедшие уже выданы poll()."""
        if not self._buffer and not self._closed:
            while self._take(block=False) and not self._buffer and not self._closed:
                pass
        return self._closed and not self._buffer

    def poll(self, limit: int) -> list[Request]:
        while len(self._buffer) < limit and not self._closed and self._take(block=False):
            pass
        taken, self._buffer = self._buffer[:max(limit, 0)], self._buffer[max(limit, 0):]
        return taken

    def wait(self) -> None:
        if not self._buffer and not self._closed:
            self._take(block=True)


def _engine_main(engine_fn, model_seed, max_batch, cpus, inq, out):
    try:
        os.sched_setaffinity(0, cpus)
        import torch

        import tinygpt
        torch.set_num_threads(len(cpus))
        model = tinygpt.make_model(seed=model_seed)
        tok, kv = model.prefill([1, 2, 3])  # прогрев
        warm = tinygpt.KVBatch()
        warm.add(kv)
        model.decode_step(warm, torch.tensor([tok]))
        out.put(("ready",))
        engine_fn(model, Inbox(inq, out), max_batch)
        out.put(("exit",))
    except BaseException:  # noqa: BLE001
        out.put(("crash", traceback.format_exc()))


def run_engine(engine_fn, *, model_seed: int, max_batch: int, rps: float, duration_s: float, mix: Mix,
               service_cpus: set[int], load_cpu: int, stall_s: float = STALL_S) -> Result:
    with _pinned(load_cpu):
        return _once_with_retry(lambda: _run_engine(engine_fn, model_seed, max_batch, rps, duration_s, mix,
                                                    service_cpus, load_cpu, stall_s))


def _run_engine(engine_fn, model_seed, max_batch, rps, duration_s, mix, service_cpus, load_cpu, stall_s):
    ctx = mp.get_context("spawn")
    inq, out = ctx.Queue(), ctx.Queue()
    proc = ctx.Process(target=_engine_main, args=(engine_fn, model_seed, max_batch, service_cpus, inq, out),
                       daemon=True)
    proc.start()
    try:
        msg = _get(out, _READY_TIMEOUT_S, proc)
        if msg[0] == "crash":
            raise EngineCrashed(msg[1])
        if msg[0] != "ready":
            raise EngineCrashed(f"движок не запустился: {msg!r}")
        return _drive(proc, inq, out, rps, duration_s, mix, stall_s)
    finally:
        if proc.is_alive():
            proc.kill()
        proc.join(5)


def _get(out, timeout, proc):
    try:
        return out.get(timeout=timeout)
    except queue.Empty:
        if not proc.is_alive():
            raise EngineCrashed(f"процесс движка завершился с кодом {proc.exitcode}") from None
        raise EngineCrashed(f"движок не ответил за {timeout:.0f} с") from None


def _drive(proc, inq, out, rps, duration_s, mix, stall_s) -> Result:
    jobs = mix.requests(max(1, int(rps * duration_s)))
    sent_at: dict[int, float] = {}
    times: dict[int, list[float]] = {i: [] for i in range(len(jobs))}
    tokens: dict[int, list[int]] = {i: [] for i in range(len(jobs))}
    lag = [0.0]
    t0 = time.perf_counter() + 0.05

    def sender():
        for i, (_, prompt, max_new) in enumerate(jobs):
            due = t0 + i / rps
            delay = due - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            lag[0] = max(lag[0], time.perf_counter() - due)
            sent_at[i] = due
            inq.put((i, prompt, max_new))
        inq.put(None)

    thread = threading.Thread(target=sender, daemon=True)
    thread.start()
    remaining = {i: max_new for i, (_, _, max_new) in enumerate(jobs)}
    last_token = time.monotonic()
    while remaining:
        try:
            msg = out.get(timeout=0.5)
        except queue.Empty:
            if not proc.is_alive():
                raise EngineCrashed(f"процесс движка завершился с кодом {proc.exitcode}") from None
            waiting = thread.is_alive() is False or any(i in sent_at for i in remaining)
            if waiting and time.monotonic() - last_token > stall_s:
                proc.kill()
                proc.join(5)
                raise EngineStalled(
                    f"за {stall_s:.0f} с не пришло ни одного токена: {len(remaining)} запросов не закончены. "
                    "Движок не убирает закончившиеся запросы или не принимает новые?", proc.pid) from None
            continue
        now = time.perf_counter()
        if msg[0] == "tok":
            _, rid, token = msg
            times[rid].append(now)
            tokens[rid].append(token)
            last_token = time.monotonic()
            if rid in remaining:
                remaining[rid] -= 1
                if remaining[rid] <= 0:
                    del remaining[rid]
        elif msg[0] == "crash":
            raise EngineCrashed(msg[1])
        elif msg[0] == "exit":
            if remaining:
                raise EngineCrashed(f"движок вернул управление, а {len(remaining)} запросов не закончены")
    thread.join()
    if lag[0] > MAX_LAG_S:
        raise LoadGeneratorLagging(f"генератор отстал от расписания на {lag[0] * 1000:.0f} мс")
    wall = max(t for ts in times.values() for t in ts) - t0 if any(times.values()) else 0.0
    recs = []
    for i, (cls, prompt, max_new) in enumerate(jobs):
        ts = times[i]
        recs.append(Rec(cls=cls, prompt=prompt, max_new=max_new,
                        ttft_s=ts[0] - sent_at[i] if ts else None,
                        e2e_s=ts[-1] - sent_at[i] if ts else None,
                        tokens=tokens[i], n_tokens=len(ts),
                        itl_s=[b - a for a, b in zip(ts, ts[1:])]))
    return Result(recs, duration_s=duration_s, wall_s=wall)


# --- HTTP: /v1/completions со стримингом ---------------------------------------------

def run_http(url: str, model: str, *, rps: float, duration_s: float, mix: Mix, load_cpu: int,
             prompts: list[str] | None = None) -> Result:
    """prompts — свои тексты промптов (по кругу); по умолчанию — prompt_text из Mix."""
    with _pinned(load_cpu):
        return _once_with_retry(lambda: asyncio.run(_run_http(url, model, rps, duration_s, mix, prompts)))


def _host_port(url: str) -> tuple[str, int]:
    rest = url.split("://", 1)[1].rstrip("/")
    host, _, port = rest.partition(":")
    return host, int(port or 80)


async def _one(host, port, model, text, max_new, due) -> tuple[list[float], int, str | None]:
    body = json.dumps({"model": model, "prompt": text, "max_tokens": max_new, "temperature": 0,
                       "stream": True, "ignore_eos": True}).encode()
    times: list[float] = []
    usage = None
    try:
        reader, writer = await asyncio.open_connection(host, port)
        writer.write(f"POST /v1/completions HTTP/1.1\r\nHost: {host}\r\nContent-Type: application/json\r\n"
                     f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
        await writer.drain()
        status = (await reader.readline()).decode(errors="replace").strip()
        if " 200 " not in status + " ":
            rest = await reader.read()
            writer.close()
            return times, 0, f"{status}: {rest.decode(errors='replace')[-300:]}"
        async for line in reader:
            line = line.strip()
            if not line.startswith(b"data:") or line.endswith(b"[DONE]"):
                continue
            try:
                chunk = json.loads(line[5:])
            except ValueError:
                continue
            if chunk.get("usage"):
                usage = chunk["usage"].get("completion_tokens", usage)
            choices = chunk.get("choices") or []
            if choices and choices[0].get("text"):
                times.append(time.perf_counter())
        writer.close()
    except OSError as exc:
        return times, 0, repr(exc)
    return times, usage if usage is not None else len(times), None


async def _run_http(url, model, rps, duration_s, mix, prompts) -> Result:
    host, port = _host_port(url)
    jobs = mix.requests(max(1, int(rps * duration_s)))
    t0 = time.perf_counter() + 0.05
    lag = 0.0
    tasks = []
    for i, (_, prompt, max_new) in enumerate(jobs):
        due = t0 + i / rps
        delay = due - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)
        lag = max(lag, time.perf_counter() - due)
        text = prompts[i % len(prompts)] if prompts else prompt_text(prompt)
        tasks.append(asyncio.create_task(_one(host, port, model, text, max_new, due)))
    done = await asyncio.wait_for(asyncio.gather(*tasks), timeout=DRAIN_S + duration_s)
    if lag > MAX_LAG_S:
        raise LoadGeneratorLagging(f"генератор отстал от расписания на {lag * 1000:.0f} мс")
    recs, last = [], t0
    for i, ((cls, prompt, max_new), (ts, n, error)) in enumerate(zip(jobs, done)):
        due = t0 + i / rps
        if ts:
            last = max(last, ts[-1])
        recs.append(Rec(cls=cls, prompt=prompt, max_new=max_new,
                        ttft_s=ts[0] - due if ts else None, e2e_s=ts[-1] - due if ts else None,
                        tokens=None, n_tokens=n, itl_s=[b - a for a, b in zip(ts, ts[1:])], error=error))
    return Result(recs, duration_s=duration_s, wall_s=last - t0)


@dataclass
class Stream:
    times: list[float]
    n_tokens: int
    error: str | None


def run_streams(url: str, model: str, plan: list[tuple[float, str, int]], *, load_cpu: int) -> tuple[float, list[Stream]]:
    """Запросы по плану [(сдвиг от старта, с; текст промпта; max_tokens)].

    Возвращает (t0, потоки): время старта по perf_counter и моменты прихода
    токенов каждого запроса — чтобы видеть, как один запрос влияет на другие.
    """
    async def go():
        host, port = _host_port(url)
        t0 = time.perf_counter() + 0.05

        async def at(offset, text, max_new):
            await asyncio.sleep(max(0.0, t0 + offset - time.perf_counter()))
            return await _one(host, port, model, text, max_new, t0 + offset)

        done = await asyncio.wait_for(asyncio.gather(*(at(*item) for item in plan)), timeout=DRAIN_S)
        return t0, [Stream(times, n, error) for times, n, error in done]

    with _pinned(load_cpu):
        return asyncio.run(go())
