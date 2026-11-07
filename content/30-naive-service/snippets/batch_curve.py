"""Сколько стоит один элемент, если звать модель батчем.

Модель та же, что в сервисе. На каждый размер батча — прогрев и REPEATS
замеров одного вызова; медиану делим на размер батча.
"""
import time

import torch

import tinymodel

BATCHES = [1, 2, 4, 8, 16, 32, 64]
REPEATS = 9


def per_item_ms(model: torch.nn.Module, batch: int) -> float:
    x = tinymodel.make_input(batch)
    with torch.inference_mode():
        model(x)  # прогрев: первый вызов на новой форме дороже
        times = []
        for _ in range(REPEATS):
            started = time.perf_counter()
            model(x)
            times.append(time.perf_counter() - started)
    times.sort()
    return 1000 * times[len(times) // 2] / batch
