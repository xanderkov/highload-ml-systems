"""Фикстура servicelib: отвечает значением заголовка X-Probe (или 400 без него)."""
from fastapi import FastAPI, Request, Response

app = FastAPI()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/predict")
async def predict(request: Request):
    await request.body()
    value = request.headers.get("x-probe")
    if value is None:
        return Response(b"no header", status_code=400)
    return Response(value.encode(), media_type="application/octet-stream")
