"""Глава 1: цена текстового протокола у Triton — KServe v2 JSON против binary extension.

Одна модель (конфиг из блока, unit_a.pbtxt), два вида тела запроса:
тензор списком чисел в JSON и тот же тензор сырыми байтами float32 после
JSON-заголовка (Inference-Header-Content-Length). Для каждого — ёмкость
(закрытый цикл) и открытая нагрузка ступенями STEP_FRACTIONS от ёмкости
бинарного варианта: те же RPS для обоих.
"""
import json
import sys

import servicelib
import stand

STEP_FRACTIONS = [0.25, 0.5, 0.75, 0.9]
STEP_S = 2.0
WARMUP_RPS, WARMUP_S = 50, 1.0


def main() -> None:
    load_cpus, _ = servicelib.split_cpus()
    inputs = stand.Inputs.make()
    config = stand.block_config()
    variants = {"binary": True, "JSON": False}
    lines = {f"{kind}: p99, мс": [] for kind in variants}

    with stand.triton_model("protocol", config) as (url, name):
        targets = {kind: stand.triton_target(url, name, inputs, binary=binary) for kind, binary in variants.items()}
        capacities = {}
        for kind, target in targets.items():
            warm = stand.load(target, WARMUP_RPS, WARMUP_S, load_cpus)
            if warm.errors or target.wrong(warm.responses, inputs):
                stand.fail(f"{kind}: прогрев — {warm.errors} ошибок, ответы не совпали с моделью "
                           f"на {target.wrong(warm.responses, inputs)} входах")
            capacities[kind] = stand.capacity(target, load_cpus)
            print(f"{kind}: тело {len(target.bodies[0]) / 1024:.0f} КиБ, ёмкость {capacities[kind]:.0f} ответов/с",
                  file=sys.stderr)
        steps = [max(10, round(capacities["binary"] * f / 10) * 10) for f in STEP_FRACTIONS]
        for rps in steps:
            for kind, target in targets.items():
                result = stand.load(target, rps, STEP_S, load_cpus)
                print(f"{kind} {rps} RPS: p50 {result.p50():.1f} мс, p99 {result.p99():.1f} мс, "
                      f"ответов/с {result.throughput():.0f}, ошибок {result.errors}", file=sys.stderr)
                lines[f"{kind}: p99, мс"].append({"x": rps, "y": round(result.p99(), 2)})

    print(json.dumps({"lines": [{"name": n, "points": p} for n, p in lines.items()]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
