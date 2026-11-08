"""Крючок раздела «Triton»: та же widemodel в Triton с минимальным конфигом.

Конфиг из блока (правка студента unit_b.pbtxt или исходный unit_a.pbtxt) —
python backend, без dynamic_batching. Харнесс грузит модель, проверяет ответы, меряет ёмкость Triton C (закрытый
цикл в PROBE_CONNECTIONS соединений) и подаёт открытую нагрузку ступенями
STEP_FRACTIONS × C. Те же ступени — сервису раздела 30 с батчем из одного
(batcher_app + batcher_starter, бинарный протокол, 3 потока torch, те же
3 CPU): так на одном графике видно, сделал ли Triton что-то сам.
Средний батч Triton — из его метрик (элементов на запуск модели).
"""
import json
import sys

import servicelib
import stand

STEP_FRACTIONS = [0.25, 0.5, 0.75, 0.9, 1.1, 1.25]
STEP_S = 2.0
WARMUP_RPS, WARMUP_S = 50, 1.0
PROBE_CONNECTIONS = 8


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
    config = stand.block_config()

    lines = {"Triton p50, мс": [], "Triton p99, мс": [], "раздел 30 p99, мс": [], "Triton: средний батч": []}
    with stand.triton_model("hook", config) as (url, name):
        triton = stand.triton_target(url, name, inputs)
        warm_up(triton, inputs, load_cpus, "Triton")
        capacity = stand.capacity(triton, load_cpus, connections=PROBE_CONNECTIONS)
        steps = [max(10, round(capacity * f / 10) * 10) for f in STEP_FRACTIONS]
        print(f"ёмкость Triton C ≈ {capacity:.0f} ответов/с; ступени {steps} RPS", file=sys.stderr)
        for rps in steps:
            meter = stand.Meter(name)
            result = stand.load(triton, rps, STEP_S, load_cpus)
            batch = stand.tritonlib.mean_batch(meter.delta())
            print(f"Triton {rps} RPS: p50 {result.p50():.1f} мс, p99 {result.p99():.1f} мс, "
                  f"ответов/с {result.throughput():.0f}, ошибок {result.errors}, средний батч {batch:.2f}",
                  file=sys.stderr)
            lines["Triton p50, мс"].append({"x": rps, "y": round(result.p50(), 2)})
            lines["Triton p99, мс"].append({"x": rps, "y": round(result.p99(), 2)})
            lines["Triton: средний батч"].append({"x": rps, "y": round(batch, 2)})

    try:
        with stand.service30("batcher_starter", service_cpus) as url:
            service = stand.service30_target(url, inputs)
            warm_up(service, inputs, load_cpus, "сервис раздела 30")
            for rps in steps:
                result = stand.load(service, rps, STEP_S, load_cpus)
                print(f"раздел 30 {rps} RPS: p50 {result.p50():.1f} мс, p99 {result.p99():.1f} мс, "
                      f"ответов/с {result.throughput():.0f}, ошибок {result.errors}", file=sys.stderr)
                lines["раздел 30 p99, мс"].append({"x": rps, "y": round(result.p99(), 2)})
    except servicelib.ServiceStartError as exc:
        stand.fail(f"сервис раздела 30: {exc}")

    print(json.dumps({"lines": [{"name": n, "points": p} for n, p in lines.items()]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
