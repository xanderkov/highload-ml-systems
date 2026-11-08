"""Длинный промпт посреди чужой генерации.

STREAMS запросов генерируют по STREAM_TOKENS токенов. Через LONG_AT_S секунд
приходит один запрос с длинным промптом (LONG_NUMBERS случайных чисел —
около 900 токенов), ему нужен один токен ответа. Смотрим, как меняются паузы
между токенами у остальных: сервер с флагами по умолчанию и с -b 64 -ub 64.
"""
import random

STREAMS = 4
STREAM_TOKENS = 120
LONG_AT_S = 1.0
LONG_NUMBERS = 150
CONFIGS = {"по умолчанию": [], "-b 64 -ub 64": ["-b", "64", "-ub", "64"]}


def long_prompt() -> str:
    rng = random.Random(0)
    return " ".join(str(rng.randrange(100000)) for _ in range(LONG_NUMBERS))
