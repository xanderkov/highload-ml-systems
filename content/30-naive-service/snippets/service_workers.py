"""Шаг 3: несколько воркеров × потоки torch (боль №2, цена по памяти — боль №1).

Сервис как на шаге 2, но uvicorn запускает WORKERS процессов, и в каждом
torch считает в TORCH_THREADS потоков. Харнесс читает эти две константы
отсюда — меняйте их и замеряйте снова. Произведение WORKERS × TORCH_THREADS
больше числа CPU сервиса обычно делает хуже, а не лучше (раздел 20, задание 2).
"""
import asyncio

import numpy as np
import torch
from fastapi import FastAPI, Request

import tinymodel

WORKERS = 2
TORCH_THREADS = 1

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
    pixels = np.frombuffer(body, dtype=np.float32).copy()
    x = torch.from_numpy(pixels).reshape(1, 3, 64, 64)
    logits = await asyncio.to_thread(infer, x)
    return {"logits": logits[0].tolist()}
