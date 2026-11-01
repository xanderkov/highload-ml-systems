from app.jobs import run_job

HARNESS = "tests/fixtures/harness/torch_import"


def job_for(harness_dir):
    return {
        "mode": "exercise",
        "lang": "python",
        "harness_dir": harness_dir,
        "units": {"a": "def total(data):\n    return 0\n", "b": "def total(data):\n    return 0\n"},
        "target": {"metric": "speedup", "op": ">=", "value": 0},
    }


def test_torch_imports_under_harness_limits():
    result = run_job(job_for(HARNESS))
    assert result["status"] == "ok", result
