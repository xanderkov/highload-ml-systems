"""Глава 5: что видно в метриках Triton и совпадает ли это с тем, что видит клиент.

Модель — конфиг блока (по умолчанию python backend с dynamic batching). На
каждой ступени STEPS харнесс снимает счётчики /metrics до и после и делит
прирост на число запросов: среднее время запроса внутри сервера, из него —
ожидание в очереди и вычисление (счётчики Triton накапливаются по запросам:
запрос в батче из четырёх добавляет время всего батча); средний батч. Рядом —
средняя latency, которую намерил клиент (генератор): разница — сеть, разбор
HTTP и всё, что сервер не считает.
"""
import json
import statistics
import sys

import servicelib
import stand
import tritonlib

STEPS = [100, 300, 700, 1100]
STEP_S = 2.0


def main() -> None:
    load_cpus, _ = servicelib.split_cpus()
    inputs = stand.Inputs.make()
    lines = {}
    with stand.triton_model("metrics", stand.block_config()) as (url, name):
        target = stand.triton_target(url, name, inputs)
        stand.load(target, 100, 0.5, load_cpus)  # прогрев
        for rps in STEPS:
            meter = stand.Meter(name)
            result = stand.load(target, rps, STEP_S, load_cpus, timeout_s=10)
            d = meter.delta()
            requests = max(d["request_success"], 1)
            server_ms = d["request_us"] / requests / 1000
            queue_ms = d["queue_us"] / requests / 1000
            compute_ms = d["compute_us"] / requests / 1000
            client_ms = statistics.fmean(result.latencies_ms) if result.latencies_ms else 0.0
            batch = tritonlib.mean_batch(d)
            print(f"{rps} RPS: клиент в среднем {client_ms:.2f} мс; сервер: запрос {server_ms:.2f} мс, "
                  f"из них очередь {queue_ms:.2f} мс и вычисление {compute_ms:.2f} мс; средний батч {batch:.1f}",
                  file=sys.stderr)
            for key, value in (("клиент: средняя latency, мс", client_ms), ("сервер: запрос целиком, мс", server_ms),
                               ("сервер: очередь, мс", queue_ms), ("сервер: вычисление, мс", compute_ms),
                               ("средний батч, штук", batch)):
                lines.setdefault(key, []).append({"x": rps, "y": round(value, 3)})
    print(json.dumps({"lines": [{"name": n, "points": p} for n, p in lines.items()]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
