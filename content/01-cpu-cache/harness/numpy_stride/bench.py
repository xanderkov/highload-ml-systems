import json
import os
import time

import numpy as np

import unit_a
import unit_b

WARMUP = int(os.environ["BENCH_WARMUP"])
REPEATS = int(os.environ["BENCH_REPEATS"])
SIZES = [int(s) for s in os.environ["BENCH_SIZES"].split(",")]

# См. комментарий в harness/py_reduce/bench.py: имя функции задаётся здесь,
# meta.function на Python-пути не читается.
FUNCTION = "reduce_stride"


def main() -> None:
    n = SIZES[0]
    # Значение зависит только от суммы индексов, поэтому матрица симметрична:
    # a[i, j] == a[j, i]. Это не украшение, а обязательное условие — два
    # варианта берут один каждый восьмой ряд и каждый восьмой столбец, и
    # только на симметричной матрице они складывают один и тот же набор
    # чисел. Иначе проверка корректности не прошла бы и сравнивать их время
    # было бы нечестно.
    index = np.arange(n, dtype=np.float64)
    data = np.add.outer(index, index) % 9973 * 0.5
    fn_a = getattr(unit_a, FUNCTION)
    fn_b = getattr(unit_b, FUNCTION)

    check_a = check_b = 0.0
    for _ in range(WARMUP):
        check_a, check_b = fn_a(data), fn_b(data)

    samples = []
    for _ in range(REPEATS):
        t0 = time.perf_counter(); check_a = fn_a(data); t1 = time.perf_counter()
        t2 = time.perf_counter(); check_b = fn_b(data); t3 = time.perf_counter()
        samples.append({"a": (t1 - t0) * 1e3, "b": (t3 - t2) * 1e3})

    print(json.dumps({"samples": samples, "check": {"a": float(check_a), "b": float(check_b)}}))


main()
