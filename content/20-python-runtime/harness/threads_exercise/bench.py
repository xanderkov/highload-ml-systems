"""Задание 2: подобрать число процессов и потоков torch в каждом.

`config(cores)` юнита возвращает (процессы, потоки). Один замер:

1. запускаем процессы через spawn (как воркеры сервиса: чистый
   интерпретатор, свой torch в каждом);
2. каждый процесс импортирует torch, ставит `torch.set_num_threads`,
   строит модель, готовит свои входы и прогревается — всё это до общего
   старта и в замер не входит;
3. по сигналу «старт» процессы делят между собой K входов (батчи по 1);
   замер — от самого раннего старта до самого позднего финиша.

check — число обработанных входов: конфигурация, которая теряет часть
работы, не зачитывается.
"""

import os

# numpy (его импортирует torch) при импорте поднимает пул OpenBLAS на все
# ядра. В задании numpy не считает ничего, а эти потоки съедают лимит задач
# runner'а: один поток на процесс. Потоки torch этим не затронуты.
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import json
import multiprocessing
import queue
import sys
import time

import unit_a
import unit_b

# Стартовая конфигурация с oversubscription тратит ~90 мс на вход (на 16
# ядрах), поэтому K небольшое: 5 повторов стартового кода — около минуты.
K = 128
WARMUP_INFERENCES = 8
MIN_CORES = 4
# Задание рассчитано на машину до MAX_CORES ядер: на большей харнесс
# привязывается к первым MAX_CORES. Так число потоков (до 4 × cores)
# остаётся в пределах лимита задач runner'а (sandbox.MAX_PROCESSES).
MAX_CORES = 32
# Верхние границы конфигурации. Больше 16 процессов не нужно, а каждый
# процесс с torch — это ~200 МиБ памяти контейнера. Всего потоков не больше
# 4 × cores: ровно столько у стартовой конфигурации.
MAX_PROCESSES = 16
MAX_THREADS_PER_CORE = 4
STAGE_TIMEOUT_S = 60


def worker(threads: int, count: int, ready, go, results) -> None:
    import torch

    import tinymodel

    torch.set_num_threads(threads)
    model = tinymodel.make_model()
    inputs = [tinymodel.make_input(1, seed=i) for i in range(count)]
    with torch.inference_mode():
        for _ in range(WARMUP_INFERENCES):
            model(inputs[0])
        ready.put(os.getpid())
        go.wait()
        # CLOCK_MONOTONIC общий для всех процессов машины: отметки разных
        # воркеров сравнимы между собой.
        t0 = time.monotonic()
        for x in inputs:
            model(x)
        t1 = time.monotonic()
    results.put((len(inputs), t0, t1))


def fail(message: str):
    print(message, file=sys.stderr)
    sys.stderr.flush()
    sys.exit(1)


def validate(name: str, config, cores: int) -> tuple[int, int]:
    prefix = f"unit {name}: config({cores}) = {config!r}:"
    if not (isinstance(config, tuple) and len(config) == 2 and all(type(v) is int for v in config)):
        fail(f"{prefix} нужен кортеж из двух int (процессы, потоки)")
    processes, threads = config
    if not 1 <= processes <= MAX_PROCESSES:
        fail(f"{prefix} число процессов должно быть от 1 до {MAX_PROCESSES}")
    if threads < 1:
        fail(f"{prefix} число потоков должно быть не меньше 1")
    if processes * threads > MAX_THREADS_PER_CORE * cores:
        fail(f"{prefix} всего потоков {processes * threads}, больше {MAX_THREADS_PER_CORE} × {cores} ядер")
    return processes, threads


def gather(source, procs, n: int, stage: str) -> list:
    """Забирает n сообщений, не дожидаясь таймаута, если воркер уже упал."""
    items = []
    deadline = time.monotonic() + STAGE_TIMEOUT_S
    while len(items) < n:
        try:
            items.append(source.get(timeout=0.05))
            continue
        except queue.Empty:
            pass
        dead = [(i + 1, p.exitcode) for i, p in enumerate(procs) if p.exitcode not in (None, 0)]
        if dead or time.monotonic() > deadline:
            for proc in procs:
                proc.kill()
            reason = f"воркеры (номер, код выхода) {dead}" if dead else f"таймаут {STAGE_TIMEOUT_S} с"
            fail(f"{stage}: {reason}")
    return items


def measure(processes: int, threads: int) -> tuple[float, int]:
    """Время (мс) на K входов при данной конфигурации и число обработанных."""
    ctx = multiprocessing.get_context("spawn")
    ready, results, go = ctx.Queue(), ctx.Queue(), ctx.Event()
    counts = [K // processes + (1 if i < K % processes else 0) for i in range(processes)]
    procs = [ctx.Process(target=worker, args=(threads, c, ready, go, results)) for c in counts]
    for proc in procs:
        proc.start()
    gather(ready, procs, processes, "воркеры не дошли до старта")
    go.set()
    records = gather(results, procs, processes, "воркеры не закончили работу")
    for proc in procs:
        proc.join()
    bad = [(i + 1, p.exitcode) for i, p in enumerate(procs) if p.exitcode != 0]
    if bad:
        fail(f"воркеры (номер, код выхода) завершились с ошибкой: {bad}")
    start = min(r[1] for r in records)
    stop = max(r[2] for r in records)
    return (stop - start) * 1000, sum(r[0] for r in records)


def main() -> None:
    cpus = sorted(os.sched_getaffinity(0))
    if len(cpus) > MAX_CORES:
        os.sched_setaffinity(0, cpus[:MAX_CORES])
    cores = len(os.sched_getaffinity(0))
    if cores < MIN_CORES:
        print(f"на машине {cores} ядер, задание требует ≥ {MIN_CORES}", file=sys.stderr)
        sys.exit(3)
    units = {"a": unit_a, "b": unit_b}
    configs = {name: validate(name, unit.config(cores), cores) for name, unit in units.items()}
    samples = []
    checks = {}
    for trial in range(-int(os.environ["BENCH_WARMUP"]), int(os.environ["BENCH_REPEATS"])):
        sample = {}
        for offset in range(2):
            name = "ab"[(trial + offset) % 2]
            ms, done = measure(*configs[name])
            print(f"unit {name}: {configs[name][0]} proc × {configs[name][1]} thr: {ms:.0f} ms", file=sys.stderr)
            sample[name] = ms
            checks[name] = float(done)
        if trial >= 0:
            samples.append(sample)
    print(json.dumps({"samples": samples, "check": checks}))


if __name__ == "__main__":
    main()
