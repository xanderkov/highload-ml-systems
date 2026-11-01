import json
import os
import random
import time
import unit_a
import unit_b

n = int(os.environ["BENCH_SIZES"].split(",")[0])
rng = random.Random(42)
# Ordinary Python objects, as returned by a JSON parser; no input NumPy array.
records = [{"id": i, "score": rng.uniform(-0.5, 1.5)} for i in range(n)]
expected = [min(1.0, max(0.0, record["score"])) for record in records]
functions = [unit_a.compute, unit_b.compute]
# Exercise empty input and a short final batch outside timing.
for fn in functions:
    for length in (0, 1, 17):
        if fn(iter(records[:length])) != expected[:length]:
            raise ValueError("Неверный результат для пустого или неполного пакета")
samples = []
for trial in range(-int(os.environ["BENCH_WARMUP"]), int(os.environ["BENCH_REPEATS"])):
    sample = {}
    for offset in range(2):
        k = (trial + offset) % 2
        stream = iter(records)
        start = time.perf_counter()
        result = functions[k](stream)
        sample["ab"[k]] = (time.perf_counter() - start) * 1000
        if not isinstance(result, list) or result != expected:
            raise ValueError("Результат не совпадает с ожидаемым")
    if trial >= 0:
        samples.append(sample)
print(json.dumps({"samples": samples, "check": {"a": 1, "b": 1}}))
