"""Шаг 2: бинарное тело (боль №4, раздел 20, подглава 5).

Клиент присылает изображение как 12 288 чисел float32 подряд (48 КиБ),
сервер смотрит на байты через `np.frombuffer` без разбора текста. Модель —
в потоке, как на шаге 1. Ответ — по-прежнему маленький JSON с 10 логитами.
"""
import asyncio

import numpy as np
import torch
from fastapi import FastAPI, Request

import tinymodel

model = tinymodel.make_model()
app = FastAPI()


def infer(x: torch.Tensor) -> torch.Tensor:
    with torch.inference_mode():
        return model(x)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/predict")
async def predict(request: Request):
    body = await request.body()
    # frombuffer смотрит в неизменяемые bytes; copy() — одна копия на 48 КиБ,
    # чтобы тензор не делил память с буфером только для чтения.
    pixels = np.frombuffer(body, dtype=np.float32).copy()
    x = torch.from_numpy(pixels).reshape(1, 3, 64, 64)
    logits = await asyncio.to_thread(infer, x)
    return {"logits": logits[0].tolist()}
