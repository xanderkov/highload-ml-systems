"""Задание «continuous batching»: движок студента против статического батча.

Юнит b — движок студента, юнит a — стартовый код (статический батч). Харнесс:

1. гоняет b на малой нагрузке и сверяет каждый ответ с генерацией этого
   запроса в одиночку: перепутанные строки — решение неверное;
2. REPEATS прогонов смеси (80 % по 16 токенов, 20 % по 128) при RPS для a и
   для b: samples — p99 TTFT коротких (мс), metrics — goodput (запросов в
   секунду с полным ответом и TTFT ≤ TTFT_SLO_S) и goodput_ratio (к a).
"""
import json
import math
import os
import statistics
import sys

import engines
import llmload
import stand
import unit_a
import unit_b

RPS = 16
DURATION_S = 6.0
MAX_BATCH = 16
TTFT_SLO_S = 0.5
REPEATS = int(os.environ.get("BENCH_REPEATS", "3"))


def main() -> None:
    check = {"a": 1.0, "b": 1.0}
    small = engines.run(unit_b.engine, "ваш код", max_batch=MAX_BATCH, rps=engines.CHECK_RPS, duration_s=engines.CHECK_S, mix=engines.CHECK_MIX)
    wrong = engines.wrong_answers(small)
    p99 = {"a": [], "b": []}
    goodput = {"a": [], "b": []}
    if wrong:
        engines.report_wrong("ваш код", wrong, small)
        check["b"] = math.nan
        p99["b"] = [DURATION_S * 1000] * REPEATS
        goodput["b"] = [0.0] * REPEATS
    units = [("a", unit_a.engine, "стартовый код")] + ([] if wrong else [("b", unit_b.engine, "ваш код")])
    for _ in range(REPEATS):
        for unit, engine, who in units:
            r = engines.run(engine, who, max_batch=MAX_BATCH, rps=RPS, duration_s=DURATION_S)
            ttft = r.ttft("short", 99)
            p99[unit].append(engines.ms(ttft) if not math.isnan(ttft) else DURATION_S * 1000)
            goodput[unit].append(r.goodput(TTFT_SLO_S))
            print(f"{who}: TTFT коротких p50 {engines.ms(r.ttft('short', 50))} мс, p99 {p99[unit][-1]} мс; "
                  f"goodput {goodput[unit][-1]:.1f} запросов/с; {r.tok_per_s():.0f} токенов/с", file=sys.stderr)
    base = max(statistics.median(goodput["a"]), 1 / DURATION_S)
    metrics = {unit: {"goodput": round(statistics.median(goodput[unit]), 1),
                      "goodput_ratio": round(statistics.median(goodput[unit]) / base, 3)} for unit in ("a", "b")}
    samples = [{"a": a, "b": b} for a, b in zip(p99["a"], p99["b"])]
    print(json.dumps({"samples": samples, "check": check, "metrics": metrics}))


if __name__ == "__main__":
    with stand.exclusive():
        main()
