"""Общее для харнессов раздела «LLM»: CPU, блокировка замеров, выход с ошибкой."""
from __future__ import annotations

import contextlib
import fcntl
import os
import sys
import time

# Сервису — не больше стольких CPU (как SERVICE_MAX_CPUS разделов 30 и 40).
SERVICE_MAX_CPUS = 3
# Та же блокировка, что у раздела «Triton»: CPU сервиса общие с сервером Triton.
LOCK_PATH = "/models/.lock"
LOCK_WAIT_S = 30


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(1)


def cpus() -> tuple[int, set[int]]:
    """(CPU генератора нагрузки, CPU сервиса): первый CPU генератору, следующие три — сервису."""
    available = sorted(os.sched_getaffinity(0))
    if len(available) < 4:
        print(f"на машине {len(available)} логических CPU, замер требует ≥ 4", file=sys.stderr)
        sys.exit(3)
    return available[0], set(available[1:1 + SERVICE_MAX_CPUS])


@contextlib.contextmanager
def exclusive(path: str = LOCK_PATH, wait_s: float = LOCK_WAIT_S):
    """CPU сервиса — только этому замеру, от подготовки до конца."""
    with open(path, "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("замер другого блока ещё идёт, ждём…", file=sys.stderr, flush=True)
            deadline = time.monotonic() + wait_s
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() > deadline:
                        fail(f"замер другого блока идёт дольше {wait_s:.0f} с; запустите этот блок позже")
                    time.sleep(0.2)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
