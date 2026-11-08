"""Задание «config.pbtxt»: goodput Triton с конфигом студента против стартового конфига.

Для каждого юнита (unit_b.pbtxt — конфиг студента, первым; unit_a.pbtxt —
стартовый конфиг без батчинга) харнесс загружает widemodel в Triton
(python backend, наш model.py), затем:

1. сверяет конфиг, как его понял сервер: max_batch_size ≥ 1, вход INPUT__0
   FP32 [3, 64, 64], выход OUTPUT__0 FP32 [10] — иначе понятное сообщение;
2. редкие запросы (RARE_COUNT штук раз в RARE_GAP_S): огромный
   max_queue_delay_microseconds держит одиночный запрос, и харнесс говорит
   об этом прямо, а не таймаутом;
3. прогрев;
4. REPEATS прогонов открытой нагрузки RPS на DURATION_S: p99, goodput при
   SLO_MS, средний батч по метрикам сервера; каждый ответ сверяется с
   выходом модели для своего входа.

Протокол kind: ab — как у задания раздела 30: samples — p99 по прогонам (мс);
check — 1.0, если все ответы совпали со своими входами, иначе NaN; metrics —
goodput, goodput_ratio (к стартовому конфигу) и mean_batch.
"""
import json
import math
import os
import statistics
import sys
from pathlib import Path

import servicelib
import stand
import tritonlib

RPS = 700
DURATION_S = 2.0
SLO_MS = 50
REPEATS = int(os.environ.get("BENCH_REPEATS", "3"))
WARMUP_RPS, WARMUP_S = 100, 0.5
RARE_GAP_S, RARE_COUNT = 0.3, 5
RARE_LIMIT_MS = 200
MAX_LOST_SHARE = 0.01


def main() -> None:
    load_cpus, _ = servicelib.split_cpus()
    inputs = stand.Inputs.make()
    p99 = {"a": [], "b": []}
    goodput = {"a": [], "b": []}
    batch = {"a": [], "b": []}
    check = {}
    # Сначала конфиг студента: ошибка в нём видна сразу, а не после замера
    # перегруженного стартового конфига.
    for unit in ("b", "a"):
        who = "стартовый конфиг" if unit == "a" else "ваш конфиг"
        config = Path(f"unit_{unit}.pbtxt").read_text(encoding="utf-8")
        wrong = lost = sent = 0
        try:
            with tritonlib.server_lock():
                name = tritonlib.unique_name(f"config-{unit}")
                with tritonlib.deploy(name, config, tritonlib.python_model_files()) as url:
                    problem = tritonlib.io_problem(tritonlib.model_config(name))
                    if problem:
                        stand.fail(f"{who}: {problem}")
                    target = stand.triton_target(url, name, inputs)
                    rare = stand.load(target, 1 / RARE_GAP_S, RARE_GAP_S * RARE_COUNT, load_cpus,
                                      timeout_s=RARE_LIMIT_MS / 1000 + 1)
                    if rare.errors or rare.p99() > RARE_LIMIT_MS:
                        stand.fail(
                            f"{who}: при редких запросах (раз в {RARE_GAP_S * 1000:.0f} мс) ответ не пришёл "
                            f"за {RARE_LIMIT_MS} мс ({rare.errors} из {len(rare.responses)} без ответа, "
                            f"p99 {rare.p99():.0f} мс). Похоже, max_queue_delay_microseconds слишком большой: "
                            f"одиночный запрос ждёт попутчиков, которых нет")
                    warm = stand.load(target, WARMUP_RPS, WARMUP_S, load_cpus)
                    if warm.errors:
                        stand.fail(f"{who}: прогрев — {warm.errors} ошибок из {len(warm.responses)} запросов")
                    wrong += target.wrong(warm.responses, inputs)
                    for _ in range(REPEATS):
                        meter = stand.Meter(name)
                        result = stand.load(target, RPS, DURATION_S, load_cpus, timeout_s=5)
                        mean = tritonlib.mean_batch(meter.delta())
                        wrong += target.wrong(result.responses, inputs)
                        lost += result.errors
                        sent += len(result.responses)
                        p99[unit].append(result.p99() if result.latencies_ms else DURATION_S * 1000)
                        goodput[unit].append(result.goodput(SLO_MS))
                        batch[unit].append(mean)
                        print(f"{who}: {RPS} RPS — p50 {result.p50():.1f} мс, p99 {result.p99():.1f} мс, "
                              f"goodput {result.goodput(SLO_MS):.0f}/с при SLO {SLO_MS} мс, "
                              f"средний батч {mean:.1f}, ошибок {result.errors}", file=sys.stderr)
        except (tritonlib.TritonUnavailable, tritonlib.TritonLoadError, tritonlib.TritonBusy) as exc:
            stand.fail(f"{who}: {exc}")
        if wrong:
            print(f"{who}: {wrong} ответов не совпали с выходом модели для своего входа", file=sys.stderr)
        too_many_lost = lost > MAX_LOST_SHARE * sent
        if too_many_lost:
            print(f"{who}: {lost} запросов из {sent} остались без ответа за 5 с", file=sys.stderr)
        check[unit] = math.nan if wrong or too_many_lost else 1.0

    base = max(statistics.median(goodput["a"]), 1 / DURATION_S)
    metrics = {
        unit: {
            "goodput": round(statistics.median(goodput[unit]), 1),
            "goodput_ratio": round(statistics.median(goodput[unit]) / base, 3),
            "mean_batch": round(statistics.median(batch[unit]), 2),
        }
        for unit in ("a", "b")
    }
    samples = [{"a": a, "b": b} for a, b in zip(p99["a"], p99["b"])]
    print(json.dumps({"samples": samples, "check": check, "metrics": metrics}))


if __name__ == "__main__":
    with stand.exclusive():
        main()
