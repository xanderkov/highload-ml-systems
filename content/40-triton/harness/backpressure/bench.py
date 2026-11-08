"""Глава 5, backpressure: очередь без границы, с таймаутом и с max_queue_size.

Конфиг блока (правка студента или исходный) — с default_queue_policy;
точки сравнения — тот же конфиг без политики (очередь без границы) и с
политикой max_queue_size: QUEUE_SIZE вместо политики блока.
Батч ограничен (max_batch_size: 4), поэтому ёмкость C умеренная; харнесс
меряет её на варианте без границы, и ступени STEP_FRACTIONS × C переходят
через неё. Отказ очереди Triton («Exceeds maximum queue size») в его метриках
отказов в нашей версии не считается, поэтому доля отказов — по ответам не 200. Линии: p99
принятых запросов и доля отказов (ответ не 200) для обоих вариантов.
"""
import json
import re
import sys

import servicelib
import stand

STEP_FRACTIONS = [0.5, 0.75, 1.0, 1.25, 1.5]
STEP_S = 3.0


QUEUE_SIZE = 8
_POLICY = re.compile(r"\s*default_queue_policy\s*:?\s*\{[^{}]*\}")


def unbounded(config: str) -> str:
    """Тот же конфиг без default_queue_policy { ... }."""
    return _POLICY.sub("", config)


def size_limited(config: str) -> str:
    """Тот же конфиг с политикой «не больше QUEUE_SIZE запросов в очереди»."""
    return re.sub(r"dynamic_batching\s*:?\s*\{", f"dynamic_batching {{\n  default_queue_policy {{ max_queue_size: {QUEUE_SIZE} }}",
                  unbounded(config), count=1)


def main() -> None:
    load_cpus, _ = servicelib.split_cpus()
    inputs = stand.Inputs.make()
    block = stand.block_config()
    if not _POLICY.search(block):
        stand.fail("в конфиге блока нет default_queue_policy внутри dynamic_batching — сравнивать не с чем")
    lines = {}
    steps = None
    variants = (("без границы", unbounded(block)), ("политика блока", block),
                (f"max_queue_size {QUEUE_SIZE}", size_limited(block)))
    for label, config in variants:
        with stand.triton_model("queue", config) as (url, name):
            # Конфиг переписан регулярным выражением — сверяем, что сервер понял его так, как задумано.
            policy = stand.tritonlib.model_config(name).get("dynamic_batching", {}).get("default_queue_policy", {})
            expected_size = QUEUE_SIZE if label.startswith("max_queue_size") else 0
            if int(policy.get("max_queue_size", 0)) != expected_size or (label == "без границы" and policy.get("timeout_action") == "REJECT"):
                stand.fail(f"«{label}»: не удалось переписать политику очереди в конфиге блока "
                           f"(сервер видит {policy}); оставьте секцию dynamic_batching {{ default_queue_policy {{ … }} }}")
            target = stand.triton_target(url, name, inputs)
            stand.load(target, 50, 0.5, load_cpus)  # прогрев
            if steps is None:
                capacity = stand.capacity(target, load_cpus)
                steps = [round(capacity * f / 10) * 10 for f in STEP_FRACTIONS]
                print(f"ёмкость C ≈ {capacity:.0f} ответов/с; ступени {steps} RPS", file=sys.stderr)
            for rps in steps:
                result = stand.load(target, rps, STEP_S, load_cpus, timeout_s=10)
                share = 100 * result.errors / len(result.responses)
                p99 = result.p99() if result.latencies_ms else 0.0
                print(f"{label}, {rps} RPS: p99 принятых {p99:.1f} мс, отказов {share:.1f} % "
                      f"ответов/с {result.throughput():.0f}",
                      file=sys.stderr)
                lines.setdefault(f"{label}: p99 принятых, мс", []).append({"x": rps, "y": round(p99, 2)})
                if label != "без границы":
                    lines.setdefault(f"{label}: отказов, %", []).append({"x": rps, "y": round(share, 2)})
    print(json.dumps({"lines": [{"name": n, "points": p} for n, p in lines.items()]}, ensure_ascii=False))


if __name__ == "__main__":
    with stand.exclusive():
        main()
