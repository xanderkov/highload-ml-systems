import pytest

from app.jobs import _parse_lines_output, run_job

HARNESS = "tests/fixtures/harness/linestest"


def job(**overrides):
    base = {
        "mode": "benchmark",
        "lang": "python",
        "harness_dir": HARNESS,
        "units": {"a": "N = 3\n"},
        "target": None,
    }
    base.update(overrides)
    return base


def test_series_returns_lines():
    result = run_job(job())

    assert result["status"] == "ok"
    assert [line["name"] for line in result["lines"]] == ["first", "second"]
    assert len(result["lines"][0]["points"]) == 3
    for field in ("speedup", "correct", "passed", "baseline_ms", "student_ms", "series"):
        assert field not in result


def test_series_student_error_is_reported():
    result = run_job(job(units={"a": "N = ("}))

    assert result["status"] == "runtime_error"


def test_c_is_no_longer_supported():
    result = run_job(job(lang="c"))

    assert result["status"] == "unsupported_lang"


@pytest.mark.parametrize(
    "stdout",
    [
        '{"lines": []}',
        '{"lines": [{"name": "a", "points": []}]}',
        '{"lines": [{"name": "a", "points": [{"x": 1}]}]}',
        '{"lines": [{"name": 1, "points": [{"x": 1, "y": 2}]}]}',
        '{"lines": [{"name": "a", "points": [{"x": "1", "y": 2}]}]}',
        '{"lines": [{"name": "a", "points": [{"x": true, "y": 2}]}]}',
        '{"series": []}',
        "",
        "not json",
    ],
)
def test_series_rejects_bad_output(stdout):
    payload, error = _parse_lines_output(stdout)

    assert payload is None and error


def test_series_accepts_well_formed_payload():
    payload, error = _parse_lines_output('{"lines": [{"name": "a", "points": [{"x": 1, "y": 2.5}]}]}')

    assert error is None
    assert payload["lines"][0]["points"][0]["y"] == 2.5
