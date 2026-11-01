import json
import os
import random
import time

import unit_a
import unit_b

count = int(os.environ["BENCH_SIZES"].split(",")[0])
rng = random.Random(42)
mixed = [1 if rng.getrandbits(1) else -1 for _ in range(count)]
grouped = [x for x in mixed if x <= 0] + [x for x in mixed if x > 0]
expected = mixed.count(1)
functions = [unit_a.sum_positive, unit_b.sum_positive]
inputs = [mixed, grouped]
checks = {}
samples = []
warmup = int(os.environ["BENCH_WARMUP"])
repeats = int(os.environ["BENCH_REPEATS"])
for trial in range(-warmup, repeats):
    sample = {}
    # Alternate execution order; preparation and checks are outside timing.
    for offset in range(2):
        index = (trial + offset) % 2
        start = time.perf_counter()
        result = functions[index](inputs[index])
        elapsed = (time.perf_counter() - start) * 1000
        key = "ab"[index]
        sample[key] = elapsed
        if result != expected:
            raise ValueError("Результат не совпадает с ожидаемым: нужна сумма положительных чисел.")
        checks[key] = result
    if trial >= 0:
        samples.append(sample)
print(json.dumps({"samples": samples, "check": checks}))
