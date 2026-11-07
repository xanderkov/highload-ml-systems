"""Задание «собрать батч»: goodput сервиса с collect_batch студента против стартового.

Для каждого юнита (unit_a — стартовый код, unit_b — код студента) харнесс
поднимает каркас batcher_app.py с этим модулем, затем:

1. редкие запросы (RARE_COUNT штук раз в RARE_GAP_S): батч, который ждёт,
   пока наберётся max_batch_size, здесь зависает — харнесс говорит об этом
   прямо, а не таймаутом. Заодно меряется CPU сервиса: при редких запросах
   он должен почти простаивать, иначе в collect_batch busy-wait;
2. прогрев;
3. REPEATS прогонов открытой нагрузки RPS на DURATION_S. По каждому — p99
   и goodput (ответов в секунду не дольше SLO_MS); каждый ответ сверяется с
   выходом модели для своего входа.

Протокол kind: ab — samples: p99 по прогонам (мс); check: 1.0, если все
ответы юнита совпали со своими входами, иначе NaN; metrics: goodput и
goodput_ratio = goodput юнита / goodput стартового кода.
"""
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import torch

import servicelib
import widemodel

HERE = Path(__file__).resolve().parent
MAX_BATCH_SIZE = 32
MAX_DELAY_S = 0.005
TORCH_THREADS = 3
RPS = 700
DURATION_S = 2.0
SLO_MS = 50
REPEATS = int(os.environ.get("BENCH_REPEATS", "3"))
WARMUP_RPS, WARMUP_S = 100, 0.5
RARE_GAP_S, RARE_COUNT = 0.3, 5
RARE_SLACK_MS = 200
BUSY_WAIT_SHARE = 0.9
INPUTS = 64
CONTENT = "application/octet-stream"


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(1)


def main() -> None:
    load_cpus, available = servicelib.split_cpus()
    cpus = servicelib.service_cpus(available)

    torch.manual_seed(1)
    inputs = torch.randn(INPUTS, 3, 64, 64)
    bodies = [x.numpy().astype(np.float32).tobytes() for x in inputs]
    torch.set_num_threads(1)
    with torch.inference_mode():
        expected = widemodel.make_model()(inputs)

    def make_body(i: int) -> bytes:
        return bodies[i % INPUTS]

    def wrong_answers(responses: list) -> int:
        wrong = 0
        for i, raw in enumerate(responses):
            if raw is None:
                continue
            got = torch.from_numpy(np.frombuffer(raw, dtype=np.float32).copy())
            if got.shape != expected[i % INPUTS].shape or not torch.allclose(got, expected[i % INPUTS], rtol=1e-4, atol=1e-4):
                wrong += 1
        return wrong

    p99 = {"a": [], "b": []}
    goodput = {"a": [], "b": []}
    check = {}
    env_base = {"MAX_BATCH_SIZE": str(MAX_BATCH_SIZE), "MAX_DELAY_S": str(MAX_DELAY_S)}
    for unit in ("a", "b"):
        who = "стартовый код" if unit == "a" else "ваш код"
        try:
            with servicelib.start_service(str(HERE / "batcher_app.py"), workers=1, torch_threads=TORCH_THREADS,
                                          cpus=cpus, env={**env_base, "BATCHER_MODULE": f"unit_{unit}"}) as url:
                cpu_before = servicelib.cpu_seconds(url.pids())
                started = time.perf_counter()
                rare = servicelib.run_load(url, rps=1 / RARE_GAP_S, duration_s=RARE_GAP_S * RARE_COUNT,
                                           make_body=make_body, content_type=CONTENT, cpus=load_cpus,
                                           timeout_s=(MAX_DELAY_S * 1000 + RARE_SLACK_MS) / 1000 + 1)
                share = (servicelib.cpu_seconds(url.pids()) - cpu_before) / (time.perf_counter() - started) / len(cpus)
                limit_ms = MAX_DELAY_S * 1000 + RARE_SLACK_MS
                if rare.errors or rare.p99() > limit_ms:
                    fail(
                        f"{who}: при редких запросах (раз в {RARE_GAP_S * 1000:.0f} мс) ответ не пришёл "
                        f"за {limit_ms:.0f} мс ({rare.errors} из {len(rare.responses)} без ответа). Похоже, батч "
                        f"не уходит, пока не наберётся max_batch_size = {MAX_BATCH_SIZE}: после первого элемента "
                        f"ждать остальных можно не дольше max_delay = {MAX_DELAY_S * 1000:.0f} мс"
                    )
                if share > BUSY_WAIT_SHARE:
                    print(f"{who}: при редких запросах сервис занимает {share:.0%} CPU — похоже на busy-wait "
                          f"в collect_batch (цикл без await, который крутится вхолостую)", file=sys.stderr)

                warm = servicelib.run_load(url, rps=WARMUP_RPS, duration_s=WARMUP_S, make_body=make_body,
                                           content_type=CONTENT, cpus=load_cpus)
                wrong = wrong_answers(warm.responses)
                for _ in range(REPEATS):
                    try:
                        result = servicelib.run_load(url, rps=RPS, duration_s=DURATION_S, make_body=make_body,
                                                     content_type=CONTENT, cpus=load_cpus, timeout_s=5)
                    except servicelib.LoadGeneratorLagging:
                        # Разовый сбой расписания генератора (соседние процессы) — один повтор.
                        result = servicelib.run_load(url, rps=RPS, duration_s=DURATION_S, make_body=make_body,
                                                     content_type=CONTENT, cpus=load_cpus, timeout_s=5)
                    wrong += wrong_answers(result.responses)
                    p99[unit].append(result.p99() if result.latencies_ms else DURATION_S * 1000)
                    goodput[unit].append(result.goodput(SLO_MS))
                    print(f"{who}: {RPS} RPS — p50 {result.p50():.1f} мс, p99 {result.p99():.1f} мс, "
                          f"goodput {result.goodput(SLO_MS):.0f}/с при SLO {SLO_MS} мс, ошибок {result.errors}",
                          file=sys.stderr)
        except servicelib.ServiceStartError as exc:
            fail(f"{who}: {exc}")
        except servicelib.LoadGeneratorLagging as exc:
            fail(f"{who}: {exc}")
        if wrong:
            print(f"{who}: {wrong} ответов не совпали с выходом модели для своего входа — "
                  f"элементы батча перепутаны или потеряны", file=sys.stderr)
        check[unit] = math.nan if wrong else 1.0

    base = max(statistics.median(goodput["a"]), 1 / DURATION_S)
    metrics = {
        unit: {
            "goodput": round(statistics.median(goodput[unit]), 1),
            "goodput_ratio": round(statistics.median(goodput[unit]) / base, 3),
        }
        for unit in ("a", "b")
    }
    samples = [{"a": a, "b": b} for a, b in zip(p99["a"], p99["b"])]
    print(json.dumps({"samples": samples, "check": check, "metrics": metrics}))


if __name__ == "__main__":
    main()
