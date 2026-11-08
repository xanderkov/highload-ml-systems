"""Глава 3: движок из блока (ваша правка) против статического батча.

unit_a — код блока: исходно стартовый (статический батч), студент вставляет
свой движок из задания. Точка сравнения — static_engine (тот же стартовый
код, копия в _lib). Оба с max_batch 16, одинаковые ступени RPS.
"""
import json
import sys

import engines
import stand
import static_engine
import unit_a

STEPS = [8, 16, 24, 32]
DURATION_S = 5.0
MAX_BATCH = 16


def main() -> None:
    small = engines.run(unit_a.engine, "ваш движок", max_batch=MAX_BATCH, rps=engines.CHECK_RPS, duration_s=engines.CHECK_S, mix=engines.CHECK_MIX)
    wrong = engines.wrong_answers(small)
    if wrong:
        engines.report_wrong("ваш движок", wrong, small)
        stand.fail("сначала добейтесь, чтобы ответы совпадали, — мерить скорость неверного движка бессмысленно")
    lines = {"ваш движок: TTFT p99 коротких, мс": [], "статический батч: TTFT p99 коротких, мс": [],
             "ваш движок: токенов/с": [], "статический батч: токенов/с": []}
    for rps in STEPS:
        for name, engine in (("ваш движок", unit_a.engine), ("статический батч", static_engine.engine)):
            r = engines.run(engine, name, max_batch=MAX_BATCH, rps=rps, duration_s=DURATION_S)
            print(f"{rps} RPS, {name}: TTFT коротких p99 {engines.ms(r.ttft('short', 99))} мс, "
                  f"e2e длинных p99 {engines.ms(r.e2e('long', 99))} мс, {r.tok_per_s():.0f} токенов/с", file=sys.stderr)
            lines[f"{name}: TTFT p99 коротких, мс"].append({"x": rps, "y": engines.ms(r.ttft("short", 99))})
            lines[f"{name}: токенов/с"].append({"x": rps, "y": round(r.tok_per_s())})
    print(json.dumps({"lines": [{"name": n, "points": p} for n, p in lines.items()]}, ensure_ascii=False))


if __name__ == "__main__":
    with stand.exclusive():
        main()
