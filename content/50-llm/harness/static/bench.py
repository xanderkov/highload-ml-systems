"""Глава 2: по одному запросу против статического батча.

Движок — unit_a.py (snippets/engine_starter.py): берёт до max_batch запросов
и крутит их, пока не закончит самый длинный. С max_batch = 1 это генерация
по одному. Нагрузка — смесь 80 % коротких ответов (16 токенов) и 20 %
длинных (128), открытый цикл, ступени RPS.
"""
import json
import sys

import engines
import stand
import unit_a

STEPS = [2, 4, 8, 12]
DURATION_S = 5.0


def main() -> None:
    lines = {"по одному: TTFT p99 коротких, мс": [], "статический батч 16: TTFT p99 коротких, мс": [],
             "статический батч 16: e2e p99 коротких, мс": []}
    for rps in STEPS:
        alone = engines.run(unit_a.engine, "по одному", max_batch=1, rps=rps, duration_s=DURATION_S)
        static = engines.run(unit_a.engine, "статический батч", max_batch=16, rps=rps, duration_s=DURATION_S)
        for name, r in (("по одному", alone), ("статический батч 16", static)):
            print(f"{rps} RPS, {name}: TTFT коротких p50 {engines.ms(r.ttft('short', 50))} мс, "
                  f"p99 {engines.ms(r.ttft('short', 99))} мс; e2e коротких p99 {engines.ms(r.e2e('short', 99))} мс, "
                  f"длинных p99 {engines.ms(r.e2e('long', 99))} мс; {r.tok_per_s():.0f} токенов/с", file=sys.stderr)
        lines["по одному: TTFT p99 коротких, мс"].append({"x": rps, "y": engines.ms(alone.ttft("short", 99))})
        lines["статический батч 16: TTFT p99 коротких, мс"].append({"x": rps, "y": engines.ms(static.ttft("short", 99))})
        lines["статический батч 16: e2e p99 коротких, мс"].append({"x": rps, "y": engines.ms(static.e2e("short", 99))})
    print(json.dumps({"lines": [{"name": n, "points": p} for n, p in lines.items()]}, ensure_ascii=False))


if __name__ == "__main__":
    with stand.exclusive():
        main()
