"""Обработчик «запроса» в асинхронном сервисе.

Харнесс вызывает handle(model, x) из event loop на каждый запрос и ждёт
результат — выход модели для батча x.
"""
import asyncio


async def handle(model, x):
    # Синхронный вызов внутри async def: пока модель считает, цикл стоит.
    return model(x)
