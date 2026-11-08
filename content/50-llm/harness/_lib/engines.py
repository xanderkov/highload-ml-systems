"""Общее для харнессов глав 2–3: прогон движка с понятными студенту ошибками."""
from __future__ import annotations

import sys

import llmload
import stand
import tinygpt

MIX = llmload.Mix()
CHECK_MIX = llmload.Mix(short=8, long=40, seed=7)
# Проверка правильности — залп: 20 запросов почти разом, больше max_batch (16).
# Строки заканчиваются в разное время (перестановки в keep), а лишние запросы
# входят в уже идущий батч. При редких запросах в батче почти всегда одна строка,
# и перепутанный порядок строк не виден.
CHECK_RPS = 100
CHECK_S = 0.2


def run(engine, who: str, *, max_batch: int, rps: float, duration_s: float, mix: llmload.Mix = MIX):
    """run_engine; падение или зависание движка — сообщение студенту и выход."""
    load_cpu, service = stand.cpus()
    try:
        return llmload.run_engine(engine, model_seed=0, max_batch=max_batch, rps=rps, duration_s=duration_s,
                                  mix=mix, service_cpus=service, load_cpu=load_cpu)
    except llmload.EngineCrashed as exc:
        stand.fail(f"{who}: движок упал.\n{exc}")
    except llmload.EngineStalled as exc:
        stand.fail(f"{who}: {exc}")


def wrong_answers(result: llmload.Result) -> list[int]:
    """Номера запросов, чьи токены не совпали с генерацией этого запроса в одиночку."""
    model = tinygpt.make_model(seed=0)
    return [i for i, rec in enumerate(result.per_request)
            if rec.tokens != tinygpt.generate_alone(model, rec.prompt, rec.max_new)]


def report_wrong(who: str, wrong: list[int], result: llmload.Result) -> None:
    rec = result.per_request[wrong[0]]
    expected = tinygpt.generate_alone(tinygpt.make_model(seed=0), rec.prompt, rec.max_new)
    print(f"{who}: {len(wrong)} ответов из {len(result.per_request)} не совпали с генерацией в одиночку. "
          f"Например, запрос {wrong[0]}: ждали {expected[:8]}…, получили {rec.tokens[:8]}…. "
          "Проверьте, что строки KVBatch, список запросов и последние токены переставляются одинаково.",
          file=sys.stderr)


def ms(value: float) -> float:
    return round(value * 1000, 1) if value == value else float("nan")
