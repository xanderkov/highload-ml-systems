"""Задание «бюджет KV»: SLOTS и CTX_TOTAL для llama-server.

Юнит b — числа студента, юнит a — стартовые. Харнесс проверяет числа до
старта сервера (бюджет KV_BUDGET токенов; llama.cpp не даёт слоту меньше
MIN_SLOT_CTX токенов, поэтому слотов не больше KV_BUDGET / MIN_SLOT_CTX),
поднимает llama-server -np SLOTS -c CTX_TOTAL и REPEATS раз подаёт смесь:
90 % коротких ответов по 16 токенов, 10 % длинных по 300.

samples — p99 TTFT коротких (мс); check — 1.0, если ни один ответ не обрезан
и ошибок нет; metrics — goodput (запросов в секунду с полным ответом и
TTFT ≤ TTFT_SLO_S) и goodput_ratio (b к a).
"""
import json
import math
import os
import statistics
import sys

import llama
import llmload
import stand
import unit_a
import unit_b

KV_BUDGET = 2048
MIN_SLOT_CTX = 256  # меньше llama.cpp не даёт: сам увеличивает -c (спека §7.4)
RPS = 3.5
DURATION_S = 6.0
TTFT_SLO_S = 0.5
MIX = llmload.Mix(short=16, long=300, long_frac=0.1)
REPEATS = int(os.environ.get("BENCH_REPEATS", "3"))


def values(unit, who: str) -> tuple[int, int]:
    slots, ctx = getattr(unit, "SLOTS", None), getattr(unit, "CTX_TOTAL", None)
    for name, value in (("SLOTS", slots), ("CTX_TOTAL", ctx)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            stand.fail(f"{who}: {name} должен быть целым числом ≥ 1, сейчас {value!r}")
    if ctx > KV_BUDGET:
        stand.fail(f"{who}: CTX_TOTAL = {ctx} больше бюджета KV — {KV_BUDGET} токенов")
    if slots * MIN_SLOT_CTX > KV_BUDGET:
        stand.fail(f"{who}: SLOTS = {slots} не влезает в бюджет: llama.cpp даёт слоту не меньше {MIN_SLOT_CTX} "
                   f"токенов и сам увеличит -c до {slots * MIN_SLOT_CTX}. Больше {KV_BUDGET // MIN_SLOT_CTX} "
                   "слотов в бюджет не поместится")
    return slots, ctx


def measure(slots: int, ctx: int, who: str) -> tuple[list[float], list[float], int, int]:
    load_cpu, service = stand.cpus()
    p99, goodput, truncated, errors = [], [], 0, 0
    try:
        with llama.serve(slots=slots, ctx_total=ctx, cpus=service) as url:
            llmload.run_http(url, llama.MODEL, rps=2, duration_s=1, mix=llmload.Mix(), load_cpu=load_cpu)
            for _ in range(REPEATS):
                r = llmload.run_http(url, llama.MODEL, rps=RPS, duration_s=DURATION_S, mix=MIX, load_cpu=load_cpu)
                ttft = r.ttft("short", 99)
                p99.append(round(ttft * 1000, 1) if not math.isnan(ttft) else DURATION_S * 1000)
                goodput.append(r.goodput(TTFT_SLO_S))
                truncated += r.truncated()
                errors += r.errors()
                print(f"{who} (-np {slots} -c {ctx}, в слоте {ctx // slots} токенов): TTFT коротких p99 {p99[-1]} мс, "
                      f"goodput {goodput[-1]:.2f} запросов/с, обрезано {r.truncated()}, ошибок {r.errors()}",
                      file=sys.stderr)
                if r.errors():
                    print(f"{who}: первая ошибка — {r.first_error()}", file=sys.stderr)
    except llama.LlamaStartError as exc:
        stand.fail(f"{who}: {exc}")
    return p99, goodput, truncated, errors


def main() -> None:
    b_slots, b_ctx = values(unit_b, "ваши числа")
    a_slots, a_ctx = values(unit_a, "стартовые числа")
    p99, goodput, check = {}, {}, {"a": 1.0}
    p99["b"], goodput["b"], truncated, errors = measure(b_slots, b_ctx, "ваши числа")
    check["b"] = 1.0 if truncated == 0 and errors == 0 else math.nan
    if truncated:
        print(f"ваши числа: {truncated} ответов обрезаны — в слот помещается {b_ctx // b_slots} токенов, а длинному "
              f"ответу нужно около {MIX.long + 20} (промпт и {MIX.long} токенов ответа). llama.cpp обрезает такой "
              "ответ молча: HTTP 200, finish_reason \"length\"", file=sys.stderr)
    p99["a"], goodput["a"], _, _ = measure(a_slots, a_ctx, "стартовые числа")
    if check["b"] == 1.0 and statistics.median(goodput["b"]) < RPS * 0.85:
        print(f"ваши числа: goodput {statistics.median(goodput['b']):.2f} из {RPS} запросов/с — короткие запросы "
              f"ждут свободного слота дольше {TTFT_SLO_S} с (TTFT p99 {statistics.median(p99['b'])} мс). "
              "Слотов не хватает", file=sys.stderr)
    base = max(statistics.median(goodput["a"]), 1 / DURATION_S)
    metrics = {u: {"goodput": round(statistics.median(goodput[u]), 2),
                   "goodput_ratio": round(statistics.median(goodput[u]) / base, 3)} for u in ("a", "b")}
    samples = [{"a": a, "b": b} for a, b in zip(p99["a"], p99["b"])]
    print(json.dumps({"samples": samples, "check": check, "metrics": metrics}))


if __name__ == "__main__":
    with stand.exclusive():
        main()
