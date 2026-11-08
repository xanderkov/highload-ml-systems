"""Глава 6: пауза декода, пока сервер обрабатывает чужой длинный промпт.

Настройки — unit_a.py (snippets/long_prompt.py). Для каждой конфигурации —
свой llama-server -np 8 -c 8192. Линия — самая длинная пауза между токенами
у коротких потоков в каждом окне BUCKET_S по времени от старта.
"""
import json
import sys

import llama
import llmload
import stand
import unit_a

BUCKET_S = 0.1


def main() -> None:
    load_cpu, service = stand.cpus()
    lines = []
    for name, flags in unit_a.CONFIGS.items():
        plan = [(0.0, f"Tell story number {i}", unit_a.STREAM_TOKENS) for i in range(unit_a.STREAMS)]
        plan.append((unit_a.LONG_AT_S, unit_a.long_prompt(), 1))
        try:
            with llama.serve(slots=8, ctx_total=8192, cpus=service, extra=flags) as url:
                llmload.run_http(url, llama.MODEL, rps=2, duration_s=1, mix=llmload.Mix(), load_cpu=load_cpu)
                t0, streams = llmload.run_streams(url, llama.MODEL, plan, load_cpu=load_cpu)
        except llama.LlamaStartError as exc:
            stand.fail(str(exc))
        for s in streams:
            if s.error:
                stand.fail(f"{name}: запрос не прошёл — {s.error}")
        long = streams[-1]
        buckets: dict[int, float] = {}
        for s in streams[:-1]:
            for a, b in zip(s.times, s.times[1:]):
                k = int((b - t0) / BUCKET_S)
                buckets[k] = max(buckets.get(k, 0.0), b - a)
        gaps = sorted(g for s in streams[:-1] for g in (b - a for a, b in zip(s.times, s.times[1:])))
        print(f"{name}: длинный промпт обработан за {long.times[0] - t0 - unit_a.LONG_AT_S:.2f} с; паузы у коротких — "
              f"медиана {gaps[len(gaps) // 2] * 1000:.0f} мс, максимум {gaps[-1] * 1000:.0f} мс", file=sys.stderr)
        lines.append({"name": f"{name}: самая длинная пауза, мс",
                      "points": [{"x": round(k * BUCKET_S, 1), "y": round(g * 1000, 1)} for k, g in sorted(buckets.items())]})
    print(json.dumps({"lines": lines}, ensure_ascii=False))


if __name__ == "__main__":
    with stand.exclusive():
        main()
