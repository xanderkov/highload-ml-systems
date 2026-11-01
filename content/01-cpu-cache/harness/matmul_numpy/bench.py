import json
import os
import time
for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS"):
    os.environ[name] = "1"
import numpy as np
import unit_a
import unit_b

n = int(os.environ["BENCH_SIZES"].split(",")[0])
i, j = np.indices((n, n))
A = ((i + j) % 16).astype(np.float64) / 16
B = ((i + j) % 8).astype(np.float64) / 8
A.flags.writeable = B.flags.writeable = False
out = np.empty_like(A)
# Independent exact reference: products repeat every 16 terms.
expected = np.zeros_like(A)
for k in range(16):
    expected += ((i + k) % 16) * ((k + j) % 8)
expected *= (n // 16) / 128
samples = []
for trial in range(-int(os.environ["BENCH_WARMUP"]), int(os.environ["BENCH_REPEATS"])):
    sample = {}
    for offset in range(2):
        k = (trial + offset) % 2
        out.fill(np.nan)
        start = time.perf_counter()
        [unit_a.multiply, unit_b.multiply][k](A, B, out)
        sample["ab"[k]] = (time.perf_counter() - start) * 1000
        if not np.array_equal(out, expected):
            raise ValueError("Результат не совпадает с ожидаемым")
    if trial >= 0:
        samples.append(sample)
print(json.dumps({"samples": samples, "check": {"a": 1, "b": 1}}))
