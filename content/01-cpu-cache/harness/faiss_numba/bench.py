import json
import os
import time
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[variable] = "1"
import numpy as np
import faiss
import numba
import unit_a
import unit_b

faiss.omp_set_num_threads(1)
numba.set_num_threads(1)
n = int(os.environ["BENCH_SIZES"].split(",")[0])
rng = np.random.default_rng(42)
points = rng.random((n, 2), dtype=np.float32)
queries = rng.random((64, 2), dtype=np.float32)
points.flags.writeable = queries.flags.writeable = False
index = faiss.IndexFlatL2(2)
index.add(points)
# Independent float64 reference, built outside timing.
reference_points = points.astype(np.float64)
expected = np.array([np.square(reference_points - q.astype(np.float64)).sum(axis=1).argmin() for q in queries])
functions = [unit_a.compute, unit_b.compute]
inputs = [index, points]
samples = []
for trial in range(-int(os.environ["BENCH_WARMUP"]), int(os.environ["BENCH_REPEATS"])):
    sample = {}
    for offset in range(2):
        k = (trial + offset) % 2
        start = time.perf_counter()
        result = functions[k](inputs[k], queries)
        sample["ab"[k]] = (time.perf_counter() - start) * 1000
        if not np.array_equal(result, expected):
            raise ValueError("Индексы ближайших точек не совпадают с ожидаемыми")
    if trial >= 0:
        samples.append(sample)
print(json.dumps({"samples": samples, "check": {"a": 1, "b": 1}}))
