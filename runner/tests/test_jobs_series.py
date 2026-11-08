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


def test_pbtxt_units_written_as_text_files():
    # Задание на config.pbtxt: юнит — текстовый файл, харнесс — обычный Python.
    config = 'backend: "python"\nmax_batch_size: 32'
    result = run_job(job(lang="pbtxt", harness_dir="tests/fixtures/harness/pbtxt_echo", units={"a": config}))

    assert result["status"] == "ok", result
    assert result["lines"][0]["name"] == config


def test_unknown_lang_still_rejected():
    result = run_job(job(lang="c"))

    assert result["status"] == "unsupported_lang"


def test_file_size_limit_default_is_64_mib():
    result = run_job(job(harness_dir="tests/fixtures/harness/bigfile_default", units={"a": ""}))

    assert result["status"] == "runtime_error"


def test_max_file_mb_from_meta_raises_limit():
    result = run_job(job(harness_dir="tests/fixtures/harness/bigfile_128", units={"a": ""}))

    assert result["status"] == "ok", result


def test_timeout_result_carries_stderr_tail():
    result = run_job(job(harness_dir="tests/fixtures/harness/hang_after_print", units={"a": ""}))

    assert result["status"] == "timeout"
    assert "занят другим замером" in result["log"]
