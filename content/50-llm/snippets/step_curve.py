"""Сколько стоит один шаг генерации при батче 1 … 32.

В батче B запросов, у каждого в KV-кэше уже KV_LEN токенов. Шаг —
model.decode_step: по одному новому токену каждому запросу. На каждый
размер батча — прогрев и REPEATS шагов, берём медиану.
"""
import time

import torch

import tinygpt

BATCHES = [1, 2, 4, 8, 16, 32]
KV_LEN = 64
REPEATS = 20


def step_ms(model: tinygpt.TinyGPT, batch: int) -> float:
    kv = tinygpt.KVBatch()
    for _ in range(batch):
        kv.add(model.prefill(list(range(KV_LEN)))[1])
    last = torch.zeros(batch, dtype=torch.long)
    times = []
    for i in range(REPEATS + 5):
        started = time.perf_counter()
        model.decode_step(kv, last)
        if i >= 5:  # первые шаги — прогрев
            times.append(time.perf_counter() - started)
    times.sort()
    return 1000 * times[len(times) // 2]
