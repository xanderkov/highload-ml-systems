"""Фикстура servicelib: мгновенный ответ."""
from fastapi import FastAPI, Request, Response

app = FastAPI()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/predict")
async def predict(request: Request):
    await request.body()
    return Response(b"ok", media_type="application/octet-stream")
