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


def test_torch_runs_under_threads_auto_within_memory_cap():
    result = run_job(job_for("tests/fixtures/harness/torch_import_auto"))
    assert result["status"] == "ok", result
