from fastapi.testclient import TestClient

from app.main import app


def read(name):
    with open(f"tests/fixtures/snippets/{name}", encoding="utf-8") as handle:
        return handle.read()


def test_run_endpoint_returns_result():
    client = TestClient(app)

    response = client.post(
        "/run",
        json={
            "mode": "exercise",
            "lang": "c",
            "harness_dir": "tests/fixtures/harness/sumtest",
            "units": {"a": read("sumtest_slow.c"), "b": read("sumtest_fast.c")},
            "target": {"metric": "speedup", "op": ">=", "value": 1.2},
            "timeout_s": 30,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_run_endpoint_supports_python_jobs():
    client = TestClient(app)

    response = client.post(
        "/run",
        json={
            "mode": "exercise",
            "lang": "python",
            "harness_dir": "tests/fixtures/harness/pytest_sum",
            "units": {"a": read("pysum_slow.py"), "b": read("pysum_fast.py")},
            "target": {"metric": "speedup", "op": ">=", "value": 10},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["passed"] is True
