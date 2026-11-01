"""Фикстура servicelib: каждый ответ 200 мс, без конкурентности (блокирующий sleep в async)."""
import time

from fastapi import FastAPI, Request, Response

app = FastAPI()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/predict")
async def predict(request: Request):
    await request.body()
    time.sleep(0.2)  # блокирует event loop: запросы обслуживаются строго по одному
    return Response(b"slow", media_type="application/octet-stream")
