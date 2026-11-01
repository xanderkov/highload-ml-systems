from fastapi import FastAPI

from app.jobs import run_job
from app.cache_info import get_cache_info

app = FastAPI(title="Runner")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run")
def run(job: dict) -> dict:
    return run_job(job)


@app.get("/cache-info")
def cache_info() -> dict:
    return get_cache_info()
