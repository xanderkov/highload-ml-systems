"""Глава 2: Triton с конфигом из блока против своего батчера из раздела 30.

Конфиг блока (правка студента unit_b.pbtxt или исходный unit_a.pbtxt) и
эталонный батчер раздела 30 (batcher_app + batcher_ref: max_batch_size 32,
max_delay 5 мс, 3 потока torch, те же 3 CPU) получают одинаковые ступени
открытой нагрузки STEPS. Линии: p99 обоих и средний батч Triton по его
метрикам.
"""
import json
import sys

import servicelib
import stand

STEPS = [100, 300, 500, 700, 900, 1100]
STEP_S = 2.0
WARMUP_RPS, WARMUP_S = 50, 1.0


def warm_up(target, inputs, load_cpus, who: str) -> None:
    warm = stand.load(target, WARMUP_RPS, WARMUP_S, load_cpus)
    if warm.errors:
        stand.fail(f"{who}: прогрев — {warm.errors} ошибок из {len(warm.responses)} запросов")
    if target.wrong(warm.responses, inputs):
        stand.fail(f"{who}: ответы не совпадают с выходом модели для своих входов")


def main() -> None:
    load_cpus, available = servicelib.split_cpus()
    service_cpus = servicelib.service_cpus(available)
    inputs = stand.Inputs.make()
    lines = {"Triton p99, мс": [], "свой батчер p99, мс": [], "Triton: средний батч": []}

    with stand.triton_model("batching", stand.block_config()) as (url, name):
        triton = stand.triton_target(url, name, inputs)
        warm_up(triton, inputs, load_cpus, "Triton")
        for rps in STEPS:
            meter = stand.Meter(name)
            result = stand.load(triton, rps, STEP_S, load_cpus)
            batch = stand.tritonlib.mean_batch(meter.delta())
            print(f"Triton {rps} RPS: p50 {result.p50():.1f} мс, p99 {result.p99():.1f} мс, "
                  f"ответов/с {result.throughput():.0f}, ошибок {result.errors}, средний батч {batch:.1f}",
                  file=sys.stderr)
            lines["Triton p99, мс"].append({"x": rps, "y": round(result.p99(), 2)})
            lines["Triton: средний батч"].append({"x": rps, "y": round(batch, 2)})

    try:
        with stand.service30("batcher_ref", service_cpus) as url:
            service = stand.service30_target(url, inputs)
            warm_up(service, inputs, load_cpus, "свой батчер")
            for rps in STEPS:
                result = stand.load(service, rps, STEP_S, load_cpus)
                print(f"свой батчер {rps} RPS: p50 {result.p50():.1f} мс, p99 {result.p99():.1f} мс, "
                      f"ответов/с {result.throughput():.0f}, ошибок {result.errors}", file=sys.stderr)
                lines["свой батчер p99, мс"].append({"x": rps, "y": round(result.p99(), 2)})
    except servicelib.ServiceStartError as exc:
        stand.fail(f"свой батчер: {exc}")

    print(json.dumps({"lines": [{"name": n, "points": p} for n, p in lines.items()]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
