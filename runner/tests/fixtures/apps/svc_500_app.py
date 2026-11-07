"""Сервис, который здоров, но на /predict всегда отвечает 500."""
from fastapi import FastAPI, Response

app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/predict")
async def predict():
    return Response(status_code=500)
