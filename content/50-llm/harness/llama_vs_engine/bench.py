"""Глава 4: выигрыш от батча у своего движка и у llama-server.

Настройки — unit_a.py (snippets/burst_gain.py). Залп из N запросов по TOKENS
токенов; выигрыш — токенов в секунду при N, делённое на токенов в секунду
при одном запросе. Свой движок — эталон задания (engine_ref в _lib).
"""
import json
import sys

import engine_ref
import engines
import llama
import llmload
import stand
import unit_a

BURST_RPS = 1000  # «почти разом»: N запросов за N мс


def burst_mix() -> llmload.Mix:
    return llmload.Mix(short=unit_a.TOKENS, long=unit_a.TOKENS)


def gains(measure) -> tuple[list[dict], dict[int, float]]:
    """Точки «выигрыш при N запросах»; база — один запрос (меряется всегда)."""
    rates = {n: measure(n) for n in sorted({1, *unit_a.BURSTS})}
    return [{"x": n, "y": round(rates[n] / rates[1], 2)} for n in unit_a.BURSTS], rates


def main() -> None:
    load_cpu, service = stand.cpus()

    def own(n: int) -> float:
        r = engines.run(engine_ref.engine, "свой движок", max_batch=16, rps=BURST_RPS, duration_s=n / BURST_RPS,
                        mix=burst_mix())
        return r.tok_per_s()

    own_points, own_rates = gains(own)
    with llama.serve(slots=16, ctx_total=16 * 256, cpus=service) as url:
        llmload.run_http(url, llama.MODEL, rps=2, duration_s=1, mix=llmload.Mix(), load_cpu=load_cpu)

        def server(n: int) -> float:
            r = llmload.run_http(url, llama.MODEL, rps=BURST_RPS, duration_s=n / BURST_RPS, mix=burst_mix(),
                                 load_cpu=load_cpu)
            if r.errors():
                stand.fail(f"llama-server: {r.errors()} ошибок, первая: {r.first_error()}")
            return r.tok_per_s()

        llama_points, llama_rates = gains(server)
    for n in sorted(own_rates):
        print(f"{n} запросов разом: свой движок {own_rates[n]:.0f} токенов/с, llama.cpp {llama_rates[n]:.0f} токенов/с",
              file=sys.stderr)
    print(json.dumps({"lines": [{"name": "свой движок (tinygpt, 30 M, fp32)", "points": own_points},
                                {"name": "llama.cpp (Qwen2.5-0.5B, q8)", "points": llama_points}]},
                     ensure_ascii=False))


if __name__ == "__main__":
    with stand.exclusive():
        main()
