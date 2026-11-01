import json
import os
import time

import torch

WARMUP = int(os.environ["BENCH_WARMUP"])
REPEATS = int(os.environ["BENCH_REPEATS"])

torch.manual_seed(0)
layer = torch.nn.Linear(512, 512)
x = torch.randn(64, 512)


def run_once() -> float:
    with torch.no_grad():
        return float(layer(x).sum())


def main() -> None:
    for _ in range(WARMUP):
        run_once()

    samples = []
    check = 0.0
    for _ in range(REPEATS):
        t0 = time.perf_counter(); check_a = run_once(); t1 = time.perf_counter()
        t2 = time.perf_counter(); check_b = run_once(); t3 = time.perf_counter()
        samples.append({"a": (t1 - t0) * 1e3, "b": (t3 - t2) * 1e3})
        check = (check_a, check_b)

    print(json.dumps({"samples": samples, "check": {"a": check[0], "b": check[1]}}))


main()
