from fastapi import FastAPI

from app.jobs import run_job

app = FastAPI(title="Runner")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run")
def run(job: dict) -> dict:
    return run_job(job)
