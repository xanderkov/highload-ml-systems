"""Глава 6, необязательно: vLLM под смесью подглавы 4.

Сервис vllm запускается вручную (профиль compose `vllm`); если его нет или
он ещё грузится — сообщение, как и зачем его запускать, и выход с ошибкой.
"""
import json
import sys

import llmload
import stand
import unit_a
import vllmprobe

STEP_S = 5.0


def main() -> None:
    state = vllmprobe.probe()
    if state == "loading":
        stand.fail("Сервис vllm запущен, но ещё загружает модель — подождите минуту и запустите блок снова.")
    if state != "ready":
        stand.fail(vllmprobe.HOW_TO)
    load_cpu, _ = stand.cpus()
    llmload.run_http(vllmprobe.URL, vllmprobe.MODEL, rps=2, duration_s=1, mix=llmload.Mix(), load_cpu=load_cpu)
    ttft, tokens = [], []
    for rps in unit_a.STEPS:
        r = llmload.run_http(vllmprobe.URL, vllmprobe.MODEL, rps=rps, duration_s=STEP_S, mix=llmload.Mix(),
                             load_cpu=load_cpu)
        if r.errors():
            stand.fail(f"vLLM, {rps} RPS: {r.errors()} ошибок, первая: {r.first_error()}")
        print(f"vLLM, {rps} RPS: TTFT коротких p99 {r.ttft('short', 99) * 1000:.0f} мс, межтокенное p50 "
              f"{r.itl(50) * 1000:.0f} мс, e2e длинных p99 {r.e2e('long', 99):.2f} с, {r.tok_per_s():.0f} токенов/с",
              file=sys.stderr)
        ttft.append({"x": rps, "y": round(r.ttft("short", 99) * 1000, 1)})
        tokens.append({"x": rps, "y": round(r.tok_per_s())})
    print(json.dumps({"lines": [{"name": "vLLM: TTFT p99 коротких, мс", "points": ttft},
                                {"name": "vLLM: токенов в секунду", "points": tokens}]}, ensure_ascii=False))


if __name__ == "__main__":
    with stand.exclusive():
        main()
