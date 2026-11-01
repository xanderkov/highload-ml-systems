"""Эксперимент: что ускоряют потоки Python, а что нет.

Для каждой нагрузки из юнита TASKS одинаковых задач делятся поровну между
1, 2 и 4 потоками; y — ускорение относительно одного потока (медиана из
REPEATS замеров). Чистый Python держит GIL всё время и не ускоряется;
numpy.matmul и инференс torch отпускают GIL внутри вызова.
"""

import os

# BLAS numpy — один поток на вызов: иначе numpy.matmul параллелится сам и
# показывает не потоки Python, а OpenBLAS. Задаётся до импорта numpy.
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import json
import statistics
import sys
import threading
import time

import unit_a

THREADS = (1, 2, 4)
REPEATS = 3
WORKLOADS = (
    ("чистый Python", unit_a.pure_python),
    ("numpy.matmul", unit_a.numpy_matmul),
    ("torch", unit_a.torch_infer),
)


def run(work, n_threads: int) -> float:
    """Время (с) на TASKS задач, поделённых между n_threads потоками."""
    per_thread = unit_a.TASKS // n_threads
    barrier = threading.Barrier(n_threads + 1)
    errors = []

    def body() -> None:
        barrier.wait()
        try:
            for _ in range(per_thread):
                work()
        except BaseException as exc:  # noqa: BLE001 — передаём в главный поток
            errors.append(exc)

    threads = [threading.Thread(target=body) for _ in range(n_threads)]
    for thread in threads:
        thread.start()
    barrier.wait()
    t0 = time.perf_counter()
    for thread in threads:
        thread.join()
    elapsed = time.perf_counter() - t0
    if errors:
        raise errors[0]
    return elapsed


def main() -> None:
    lines = []
    for name, work in WORKLOADS:
        run(work, 1)  # прогрев: первые вызовы numpy и torch дороже
        times = {n: statistics.median(run(work, n) for _ in range(REPEATS)) for n in THREADS}
        speedups = {n: times[1] / times[n] for n in THREADS}
        print(
            f"{name}: " + ", ".join(f"{n} thr {times[n] * 1000:.0f} ms ({speedups[n]:.2f}x)" for n in THREADS),
            file=sys.stderr,
        )
        lines.append({"name": name, "points": [{"x": n, "y": round(speedups[n], 2)} for n in THREADS]})
    print(json.dumps({"lines": lines}))


main()
