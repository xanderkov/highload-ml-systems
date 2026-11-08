"""Глава 4: llama-server с 1, 4, 16 слотами под той же смесью запросов.

Настройки — unit_a.py (snippets/llama_slots.py). Для каждого числа слотов —
свой сервер (-np и -c меняются только перезапуском), прогрев, затем ступени
открытой нагрузки по STEP_S секунд.
"""
import json
import sys

import llama
import llmload
import stand
import unit_a

STEP_S = 5.0
MAX_SLOTS = 64
MAX_STEPS = 6
MAX_RPS = 16


def check_settings() -> None:
    slots, steps = unit_a.SLOTS, unit_a.STEPS
    if not slots or not all(isinstance(s, int) and 1 <= s <= MAX_SLOTS for s in slots):
        stand.fail(f"SLOTS — список целых от 1 до {MAX_SLOTS}")
    if not isinstance(unit_a.CTX_PER_SLOT, int) or unit_a.CTX_PER_SLOT < 160:
        stand.fail("CTX_PER_SLOT — целое ≥ 160: в слот должны поместиться промпт и длинный ответ (128 токенов)")
    if max(slots) * unit_a.CTX_PER_SLOT > llama.KV_BUDGET:
        stand.fail(f"max(SLOTS) × CTX_PER_SLOT = {max(slots) * unit_a.CTX_PER_SLOT} — больше {llama.KV_BUDGET} "
                   "токенов KV: под ограничением памяти задания сервер не стартует")
    if not steps or len(steps) > MAX_STEPS or not all(0 < r <= MAX_RPS for r in steps):
        stand.fail(f"STEPS — до {MAX_STEPS} ступеней, каждая от 0 до {MAX_RPS} запросов в секунду")


def main() -> None:
    check_settings()
    load_cpu, service = stand.cpus()
    lines = {}
    for slots in unit_a.SLOTS:
        ttft = lines.setdefault(f"-np {slots}: TTFT p99 коротких, мс", [])
        try:
            with llama.serve(slots=slots, ctx_total=slots * unit_a.CTX_PER_SLOT, cpus=service) as url:
                llmload.run_http(url, llama.MODEL, rps=2, duration_s=1, mix=llmload.Mix(), load_cpu=load_cpu)
                for rps in unit_a.STEPS:
                    r = llmload.run_http(url, llama.MODEL, rps=rps, duration_s=STEP_S, mix=llmload.Mix(),
                                         load_cpu=load_cpu)
                    if r.errors():
                        stand.fail(f"-np {slots}, {rps} RPS: {r.errors()} ошибок, первая: {r.first_error()}")
                    print(f"-np {slots}, {rps} RPS: TTFT коротких p50 {r.ttft('short', 50) * 1000:.0f} мс, "
                          f"p99 {r.ttft('short', 99) * 1000:.0f} мс; межтокенное p50 {r.itl(50) * 1000:.0f} мс; "
                          f"e2e длинных p99 {r.e2e('long', 99):.2f} с; {r.tok_per_s():.0f} токенов/с", file=sys.stderr)
                    ttft.append({"x": rps, "y": round(r.ttft("short", 99) * 1000, 1)})
        except llama.LlamaStartError as exc:
            stand.fail(str(exc))
    print(json.dumps({"lines": [{"name": n, "points": p} for n, p in lines.items()]}, ensure_ascii=False))


if __name__ == "__main__":
    with stand.exclusive():
        main()
