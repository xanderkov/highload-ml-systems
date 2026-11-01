import json
import math
import os
import time
import numpy as np
import unit_a
import unit_b

n = int(os.environ["BENCH_SIZES"].split(",")[0])
data = np.random.default_rng(42).uniform(-2.0, 2.0, n)
data.flags.writeable = False
expected = float(np.square(np.clip(data, -1.0, 1.0)).sum())
functions = [unit_a.compute, unit_b.compute]
samples = []
checks = {}
for trial in range(-int(os.environ["BENCH_WARMUP"]), int(os.environ["BENCH_REPEATS"])):
    sample = {}
    for offset in range(2):
        k = (trial + offset) % 2
        start = time.perf_counter()
        value = float(functions[k](data))
        sample["ab"[k]] = (time.perf_counter() - start) * 1000
        if not math.isclose(value, expected, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError("Результат не совпадает с ожидаемым")
        checks["ab"[k]] = value
    if trial >= 0:
        samples.append(sample)
print(json.dumps({"samples": samples, "check": checks}))
