"""Шаг 1: модель — в потоке (боль №3, раздел 20, подглава 4).

Тот же сервис, но вызов модели уходит в пул потоков через
`asyncio.to_thread`: пока поток считает свёртку (torch отпускает GIL), event
loop принимает и разбирает следующие запросы. Тело по-прежнему JSON.
"""
import asyncio

import torch
from fastapi import FastAPI, Request

import tinymodel

model = tinymodel.make_model()
app = FastAPI()


def infer(x: torch.Tensor) -> torch.Tensor:
    # inference_mode действует только в своём потоке — включаем его здесь.
    with torch.inference_mode():
        return model(x)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/predict")
async def predict(request: Request):
    pixels = await request.json()
    x = torch.tensor(pixels, dtype=torch.float32).reshape(1, 3, 64, 64)
    logits = await asyncio.to_thread(infer, x)
    return {"logits": logits[0].tolist()}
