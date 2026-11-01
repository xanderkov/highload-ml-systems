from app.jobs import _parse_sweep_output, run_job

HARNESS = "tests/fixtures/harness/sweeptest"
SIZES = [64, 8192, 2000000]


def read(name):
    with open(f"tests/fixtures/snippets/{name}", encoding="utf-8") as handle:
        return handle.read()


def job(units, **overrides):
    base = {
        "lang": "c",
        "harness_dir": HARNESS,
        "units": units,
        "timeout_s": 5,
    }
    base.update(overrides)
    return base


def test_sweep_returns_series_without_ab_fields():
    result = run_job(job({"a": read("sweeptest_touch.c")}))

    assert result["status"] == "ok"
    assert "-O2" in result["compile_command"]

    # A sweep has no baseline, no speedup, no verdict, no correctness check —
    # just points. Emitting any of these would look like a real comparison.
    for field in ("speedup", "correct", "passed", "baseline_ms", "student_ms", "spread_pct"):
        assert field not in result

    sizes = [point["size"] for point in result["series"]]
    assert sizes == SIZES


def test_sweep_series_grows_with_size():
    result = run_job(job({"a": read("sweeptest_touch.c")}))

    # Sizes span three orders of magnitude on a simple O(n) scan, so total
    # time must grow with size on any real machine — this pins that real,
    # varying-size measurement happened, without asserting anything about
    # where the cache plateaus actually land (that's hardware-dependent).
    times = [point["ms"] for point in result["series"]]
    assert times[0] < times[1] < times[2]

    per_element = [point["ms_per_element"] for point in result["series"]]
    assert all(v > 0 for v in per_element)


def test_sweep_compile_error_is_reported():
    result = run_job(job({"a": "не код"}))

    assert result["status"] == "compile_error"


def test_sweep_infinite_loop_reports_timeout():
    slow = "double touch(const double *d, int n){ (void)d; (void)n; volatile int spin = 1; while (spin) { } return 0; }"
    result = run_job(job({"a": slow}))

    assert result["status"] == "timeout"


def test_sweep_rejects_series_length_mismatch():
    payload, error = _parse_sweep_output(
        '{"series": [{"size": 1, "ms": 1.0, "ms_per_element": 1.0}]}', expected_points=3
    )

    assert payload is None
    assert error


def test_sweep_rejects_point_missing_size_or_ms_per_element():
    payload, error = _parse_sweep_output(
        '{"series": [{"ms": 1.0, "ms_per_element": 1.0}]}', expected_points=1
    )

    assert payload is None
    assert error


def test_sweep_rejects_empty_series():
    payload, error = _parse_sweep_output('{"series": []}', expected_points=1)

    assert payload is None
    assert error


def test_sweep_rejects_missing_series_key():
    payload, error = _parse_sweep_output('{"samples": []}', expected_points=1)

    assert payload is None
    assert error


def test_sweep_rejects_unparseable_json():
    payload, error = _parse_sweep_output("not json", expected_points=1)

    assert payload is None
    assert error


def test_sweep_rejects_empty_stdout():
    payload, error = _parse_sweep_output("", expected_points=1)

    assert payload is None
    assert error


def test_sweep_accepts_well_formed_payload():
    payload, error = _parse_sweep_output(
        '{"series": [{"size": 10, "ms": 1.0, "ms_per_element": 0.1}]}', expected_points=1
    )

    assert error is None
    assert payload["series"][0]["size"] == 10
