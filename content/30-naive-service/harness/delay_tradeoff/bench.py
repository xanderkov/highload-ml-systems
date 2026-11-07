"""Компромисс latency ↔ throughput: как max_queue_delay двигает p50 и p99.

Каркас batcher_app.py с collect_batch из блока (unit_b — правка студента,
иначе unit_a — эталон). Для каждого max_queue_delay из DELAYS_MS сервис
поднимается заново и получает две открытые нагрузки: редкую (LOW_RPS) и
плотную (HIGH_RPS, та же, что в задании). Остальное — как в задании:
три CPU, torch в TORCH_THREADS потока, max_batch_size = MAX_BATCH_SIZE.
"""
import json
import sys
from pathlib import Path

import numpy as np
import torch

import servicelib

HERE = Path(__file__).resolve().parent
DELAYS_MS = [0, 1, 2, 5, 10, 20]
LOW_RPS, HIGH_RPS = 100, 700
STEP_S = 1.5
MAX_BATCH_SIZE = 32
TORCH_THREADS = 3
CONTENT = "application/octet-stream"


def main() -> None:
    load_cpus, available = servicelib.split_cpus()
    cpus = servicelib.service_cpus(available)
    module = "unit_b" if (HERE / "unit_b.py").exists() else "unit_a"

    torch.manual_seed(1)
    bodies = [x.numpy().astype(np.float32).tobytes() for x in torch.randn(64, 3, 64, 64)]

    def make_body(i: int) -> bytes:
        return bodies[i % len(bodies)]

    lines = {f"p50 при {LOW_RPS} RPS": [], f"p99 при {LOW_RPS} RPS": [],
             f"p50 при {HIGH_RPS} RPS": [], f"p99 при {HIGH_RPS} RPS": []}
    for delay in DELAYS_MS:
        env = {"BATCHER_MODULE": module, "MAX_BATCH_SIZE": str(MAX_BATCH_SIZE), "MAX_DELAY_S": str(delay / 1000)}
        try:
            with servicelib.start_service(str(HERE / "batcher_app.py"), workers=1, torch_threads=TORCH_THREADS,
                                          cpus=cpus, env=env) as url:
                servicelib.run_load(url, rps=LOW_RPS, duration_s=0.3, make_body=make_body,
                                    content_type=CONTENT, cpus=load_cpus, timeout_s=5)
                for rps in (LOW_RPS, HIGH_RPS):
                    try:
                        result = servicelib.run_load(url, rps=rps, duration_s=STEP_S, make_body=make_body,
                                                     content_type=CONTENT, cpus=load_cpus, timeout_s=5)
                    except servicelib.LoadGeneratorLagging:
                        result = servicelib.run_load(url, rps=rps, duration_s=STEP_S, make_body=make_body,
                                                     content_type=CONTENT, cpus=load_cpus, timeout_s=5)
                    if not result.latencies_ms:
                        print(f"max_queue_delay {delay} мс, {rps} RPS: ни одного ответа", file=sys.stderr)
                        sys.exit(1)
                    print(f"max_queue_delay {delay} мс, {rps} RPS: p50 {result.p50():.1f} мс, "
                          f"p99 {result.p99():.1f} мс, ответов/с {result.throughput():.0f}, ошибок {result.errors}",
                          file=sys.stderr)
                    lines[f"p50 при {rps} RPS"].append({"x": delay, "y": round(result.p50(), 2)})
                    lines[f"p99 при {rps} RPS"].append({"x": delay, "y": round(result.p99(), 2)})
        except servicelib.ServiceStartError as exc:
            print(exc, file=sys.stderr)
            sys.exit(1)
    print(json.dumps({"lines": [{"name": n, "points": p} for n, p in lines.items()]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
