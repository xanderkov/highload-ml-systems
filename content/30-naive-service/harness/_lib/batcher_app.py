"""Каркас сервиса с dynamic batching для задания подглавы 4 (не редактируется студентом).

Обработчик /predict кладёт вход в очередь вместе с future и ждёт ответ.
Фоновая задача в цикле зовёт collect_batch студента, склеивает батч, считает
модель в потоке и раздаёт строки выхода по future — i-я строка i-му элементу.
Модуль с collect_batch задаёт переменная окружения BATCHER_MODULE (unit_a —
стартовый код, unit_b — код студента); параметры батча — MAX_BATCH_SIZE и
MAX_DELAY_S. Протокол бинарный: 12 288 float32 на вход, 10 float32 в ответ.
"""
import asyncio
import contextlib
import importlib
import os
import sys
import traceback

import numpy as np
import torch
from fastapi import FastAPI, Request, Response

import widemodel

batcher = importlib.import_module(os.environ["BATCHER_MODULE"])
MAX_BATCH_SIZE = int(os.environ.get("MAX_BATCH_SIZE", "32"))
MAX_DELAY_S = float(os.environ.get("MAX_DELAY_S", "0.005"))

model = widemodel.make_model()


def infer(x: torch.Tensor) -> torch.Tensor:
    with torch.inference_mode():
        return model(x)


async def batch_loop(queue: asyncio.Queue) -> None:
    while True:
        items = await batcher.collect_batch(queue, MAX_BATCH_SIZE, MAX_DELAY_S)
        if not isinstance(items, list) or not items:
            print(f"collect_batch вернул {type(items).__name__} длины "
                  f"{len(items) if hasattr(items, '__len__') else '?'}, а нужен непустой list", file=sys.stderr)
            continue
        try:
            x = torch.stack([tensor for tensor, _ in items])
            out = await asyncio.to_thread(infer, x)
            for (_, future), row in zip(items, out):
                if not future.done():
                    future.set_result(row)
        except Exception as exc:  # noqa: BLE001 — ответить всем, а не оставить их ждать
            traceback.print_exc()
            for _, future in items:
                if not future.done():
                    future.set_exception(exc)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.queue = asyncio.Queue()
    task = asyncio.create_task(batch_loop(app.state.queue))
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/predict")
async def predict(request: Request):
    body = await request.body()
    x = torch.from_numpy(np.frombuffer(body, dtype=np.float32).copy()).reshape(3, 64, 64)
    future = asyncio.get_running_loop().create_future()
    await request.app.state.queue.put((x, future))
    row = await future
    return Response(row.numpy().astype(np.float32).tobytes(), media_type="application/octet-stream")
