import json
import os
import time

import numpy as np

import unit_a
import unit_b

WARMUP = int(os.environ["BENCH_WARMUP"])
REPEATS = int(os.environ["BENCH_REPEATS"])
SIZES = [int(s) for s in os.environ["BENCH_SIZES"].split(",")]

# Имя функции выбирается здесь, а не в meta.yml: на Python-пути runner ничего
# не переименовывает (в отличие от C, где -D<function>=fn_a делает это за
# нас) — он просто кладёт код студента в unit_b.py и импортирует модуль.
FUNCTION = "reduce_rows"


def main() -> None:
    n = SIZES[0]
    # Детерминированные данные: оба варианта обязаны получить один и тот же
    # ответ. Период 9973 — простое число, не делящее длину строки, поэтому
    # строки не повторяют друг друга.
    data = (np.arange(n * n, dtype=np.float64) % 9973 * 0.5).reshape(n, n)
    fn_a = getattr(unit_a, FUNCTION)
    fn_b = getattr(unit_b, FUNCTION)

    check_a = check_b = 0.0
    for _ in range(WARMUP):
        check_a, check_b = fn_a(data), fn_b(data)

    # Инварианты те же, что в bench.c: warmup отброшен, A и B чередуются
    # внутри повтора, наружу уходит ровно REPEATS сырых замеров — медиану
    # считает measure.ab_result.
    samples = []
    for _ in range(REPEATS):
        t0 = time.perf_counter(); check_a = fn_a(data); t1 = time.perf_counter()
        t2 = time.perf_counter(); check_b = fn_b(data); t3 = time.perf_counter()
        samples.append({"a": (t1 - t0) * 1e3, "b": (t3 - t2) * 1e3})

    print(json.dumps({"samples": samples, "check": {"a": float(check_a), "b": float(check_b)}}))


main()
