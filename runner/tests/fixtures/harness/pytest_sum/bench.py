import json
import os
import time

import numpy as np

import unit_a
import unit_b

WARMUP = int(os.environ["BENCH_WARMUP"])
REPEATS = int(os.environ["BENCH_REPEATS"])
SIZES = [int(s) for s in os.environ["BENCH_SIZES"].split(",")]


def main() -> None:
    data = np.arange(SIZES[0], dtype=np.float64) % 17 * 0.5
    fn_a, fn_b = unit_a.total, unit_b.total

    check_a = check_b = 0.0
    for _ in range(WARMUP):
        check_a, check_b = fn_a(data), fn_b(data)

    # Инварианты протокола замера те же, что в bench.c (см. sumtest):
    # warmup отброшен, A и B чередуются внутри каждого повтора, пишутся
    # только сырые замеры — медиану считает Python в measure.ab_result.
    samples = []
    for _ in range(REPEATS):
        t0 = time.perf_counter(); check_a = fn_a(data); t1 = time.perf_counter()
        t2 = time.perf_counter(); check_b = fn_b(data); t3 = time.perf_counter()
        samples.append({"a": (t1 - t0) * 1e3, "b": (t3 - t2) * 1e3})

    print(json.dumps({"samples": samples, "check": {"a": float(check_a), "b": float(check_b)}}))


main()
