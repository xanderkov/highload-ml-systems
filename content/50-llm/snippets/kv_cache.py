"""Генерация без KV-кэша и с ним: время на токен от длины ответа.

Без кэша каждый шаг заново прогоняет промпт и всё, что уже сгенерировано.
С кэшем prefill прогоняет промпт один раз, а шаг считает только новый токен:
ключи и значения прошлых токенов лежат в кэше.
"""
import time

import tinygpt

PROMPT = list(range(16))
LENGTHS = [16, 32, 64, 128, 256, 512]


def ms_per_token(model: tinygpt.TinyGPT, n: int, cached: bool) -> float:
    generate = tinygpt.generate_alone if cached else tinygpt.generate_nocache
    generate(model, PROMPT, 2)  # прогрев
    started = time.perf_counter()
    generate(model, PROMPT, n)
    return 1000 * (time.perf_counter() - started) / n
