"""Наивный сервис: так его пишут в первый раз.

FastAPI, один воркер uvicorn. Клиент присылает изображение 3×64×64 как
JSON-список из 12 288 чисел, обработчик собирает из него тензор и вызывает
модель прямо внутри `async def`. В ответ — 10 логитов, тоже JSON.
"""
import torch
from fastapi import FastAPI, Request

import tinymodel

model = tinymodel.make_model()
app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/predict")
async def predict(request: Request):
    pixels = await request.json()
    x = torch.tensor(pixels, dtype=torch.float32).reshape(1, 3, 64, 64)
    with torch.inference_mode():
        logits = model(x)
    return {"logits": logits[0].tolist()}
