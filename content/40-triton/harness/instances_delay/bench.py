"""Глава 3: окупается ли ожидание в очереди при нескольких экземплярах модели.

Конфиг блока (unit_a.pbtxt, с dynamic_batching) — шаблон: харнесс меняет в
нём число экземпляров (instance_group count), потоки torch на экземпляр
(TORCH_THREADS = 3 // экземпляров, чтобы вместе не больше 3 CPU) и
max_queue_delay_microseconds. Для каждой пары «экземпляры × задержка» —
открытая нагрузка LOW_RPS и HIGH_RPS по STEP_S. Отдельно — переподписка:
3 экземпляра по 3 потока torch (9 потоков на 3 CPU) при HIGH_RPS.
"""
import json
import re
import sys

import servicelib
import stand

INSTANCES = [1, 2, 3]
DELAYS_MS = [0, 2, 5, 10]
OVERSUBSCRIBED_DELAYS_MS = [0, 5, 10]
LOW_RPS, HIGH_RPS = 100, 700
STEP_S = 2.0
SERVER_CPUS = 3


def make_config(template: str, instances: int, threads: int, delay_ms: float) -> str:
    config = re.sub(r"count\s*:\s*\d+", f"count: {instances}", template)
    config = re.sub(r'(key\s*:\s*"TORCH_THREADS"\s*value\s*:?\s*\{\s*string_value\s*:\s*")\d+', rf"\g<1>{threads}", config)
    config = re.sub(r"\s*max_queue_delay_microseconds\s*:\s*\d+", "", config)
    return re.sub(r"dynamic_batching\s*:?\s*\{", f"dynamic_batching {{\n  max_queue_delay_microseconds: {int(delay_ms * 1000)}",
                  config, count=1)


def check_config(name: str, instances: int, threads: int, delay_ms: float) -> None:
    """Конфиг переписан регулярными выражениями — сверяем, что сервер понял его так, как задумано."""
    got = stand.tritonlib.model_config(name)
    count = sum(int(g.get("count", 1)) for g in got.get("instance_group", []))
    delay = int(got.get("dynamic_batching", {}).get("max_queue_delay_microseconds", 0))
    torch_threads = got.get("parameters", {}).get("TORCH_THREADS", {}).get("string_value")
    if (count, delay, torch_threads) != (instances, int(delay_ms * 1000), str(threads)):
        stand.fail(f"конфиг после подстановки не тот: экземпляров {count}, задержка {delay} мкс, "
                   f"потоков {torch_threads}; ожидалось {instances}, {int(delay_ms * 1000)}, {threads}")


def measure(template, inputs, load_cpus, instances, threads, delay_ms, rates):
    config = make_config(template, instances, threads, delay_ms)
    out = {}
    with stand.triton_model("instances", config) as (url, name):
        check_config(name, instances, threads, delay_ms)
        target = stand.triton_target(url, name, inputs)
        stand.load(target, LOW_RPS, 0.5, load_cpus)  # прогрев
        for rps in rates:
            meter = stand.Meter(name)
            result = stand.load(target, rps, STEP_S, load_cpus, timeout_s=5)
            if target.wrong(result.responses, inputs):
                stand.fail("ответы не совпадают с выходом модели для своих входов")
            batch = stand.tritonlib.mean_batch(meter.delta())
            print(f"{instances} экз. × {threads} пот., задержка {delay_ms} мс, {rps} RPS: p50 {result.p50():.1f} мс, "
                  f"p99 {result.p99():.1f} мс, ответов/с {result.throughput():.0f}, ошибок {result.errors}, "
                  f"средний батч {batch:.1f}", file=sys.stderr)
            out[rps] = result
    return out


def main() -> None:
    load_cpus, _ = servicelib.split_cpus()
    inputs = stand.Inputs.make()
    template = stand.block_config()
    if "dynamic_batching" not in template:
        stand.fail("в конфиге-шаблоне нет секции dynamic_batching: ожидание в очереди нечему настраивать")
    lines = {}
    for instances in INSTANCES:
        threads = max(1, SERVER_CPUS // instances)
        for delay in DELAYS_MS:
            results = measure(template, inputs, load_cpus, instances, threads, delay, [LOW_RPS, HIGH_RPS])
            if instances == 1:
                # Цена ожидания при редких запросах от числа экземпляров не зависит — одна линия.
                lines.setdefault(f"p50 при {LOW_RPS} RPS", []).append(
                    {"x": delay, "y": round(results[LOW_RPS].p50(), 2)})
            lines.setdefault(f"p99 при {HIGH_RPS} RPS, {instances} экз.", []).append(
                {"x": delay, "y": round(results[HIGH_RPS].p99(), 2)})
    for delay in OVERSUBSCRIBED_DELAYS_MS:
        results = measure(template, inputs, load_cpus, 3, SERVER_CPUS, delay, [HIGH_RPS])
        lines.setdefault(f"p99 при {HIGH_RPS} RPS, 3 экз. × 3 потока", []).append(
            {"x": delay, "y": round(results[HIGH_RPS].p99(), 2)})
    print(json.dumps({"lines": [{"name": n, "points": p} for n, p in lines.items()]}, ensure_ascii=False))


if __name__ == "__main__":
    with stand.exclusive():
        main()
