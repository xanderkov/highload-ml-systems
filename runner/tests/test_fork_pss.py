import os

from app.jobs import run_job

HARNESS = os.path.join(
    os.environ.get("CONTENT_ROOT", "/content"), "20-python-runtime", "harness", "fork_pss"
)


def job(unit):
    return {"mode": "benchmark", "lang": "python", "harness_dir": HARNESS, "units": {"a": unit}, "target": None}


def test_worker_exception_gives_runtime_error():
    unit = (
        "def build_data():\n    return {'tok0': 1}\n\n"
        "def worker(data, rounds):\n    raise ValueError('boom')\n"
    )

    result = run_job(job(unit))

    assert result["status"] == "runtime_error"
    assert "boom" in result["log"]


def test_small_worker_yields_five_lines():
    unit = (
        "def build_data():\n    return {'tok0': 1}\n\n"
        "def worker(data, rounds):\n    return data['tok0']\n"
    )

    result = run_job(job(unit))

    assert result["status"] == "ok"
    assert [line["name"] for line in result["lines"]] == [f"worker {i}" for i in range(1, 5)] + ["parent"]
