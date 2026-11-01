from app.jobs import _parse_output, run_job

HARNESS = "tests/fixtures/harness/sumtest"


def read(name):
    with open(f"tests/fixtures/snippets/{name}", encoding="utf-8") as handle:
        return handle.read()


def job(units, mode="exercise", target=None):
    return {
        "mode": mode,
        "lang": "c",
        "harness_dir": HARNESS,
        "units": units,
        "target": target or {"metric": "speedup", "op": ">=", "value": 1.2},
        "timeout_s": 3,
    }


def test_faster_correct_solution_passes():
    result = run_job(job({"a": read("sumtest_slow.c"), "b": read("sumtest_fast.c")}))

    assert result["status"] == "ok"
    assert result["correct"] is True
    assert result["speedup"] > 1.0
    assert result["passed"] is True
    assert "-O2" in result["compile_command"]


def test_wrong_answer_fails_even_if_fast():
    result = run_job(job({"a": read("sumtest_slow.c"), "b": read("sumtest_wrong.c")}))

    assert result["correct"] is False
    assert result["passed"] is False


def test_identical_code_does_not_reach_target():
    code = read("sumtest_slow.c")
    result = run_job(job({"a": code, "b": code}, target={"metric": "speedup", "op": ">=", "value": 3}))

    # A harness that ran all of A then all of B, dropped warmup incorrectly,
    # or averaged instead of taking the median could still pass "passed is
    # False" trivially (e.g. by reporting garbage). Pin the actual measured
    # ratio to a sane band around 1.0 so a broken harness would be caught
    # here rather than only failing a downstream, harder-to-diagnose test.
    assert result["status"] == "ok"
    assert 0.5 < result["speedup"] < 2.0
    assert result["passed"] is False


def test_compile_error_is_reported_to_student():
    result = run_job(job({"a": read("sumtest_slow.c"), "b": "не код"}))

    assert result["status"] == "compile_error"
    assert result["line"] == 1
    assert "error" in result["message"] or "error" in result["log"]


def test_compile_error_in_baseline_is_not_shown_to_student_as_a_line():
    # "a" is the baseline, not the student's own code. If it fails to
    # compile (a content bug, not a student mistake), the response must not
    # hand back a line number — Task 10 would highlight it in the student's
    # editor, where a line pointing at code they never wrote is worse than
    # no line at all.
    result = run_job(job({"a": "не код", "b": read("sumtest_fast.c")}))

    assert result["status"] == "compile_error"
    assert result["line"] is None


def test_infinite_loop_reports_timeout():
    # A `volatile` condition, not `while (n) {}` on a plain parameter: C11
    # lets a compiler assume a side-effect-free loop with a non-constant
    # condition terminates, so a future compiler could legally delete a
    # naive infinite loop and turn this into a confusing non-timeout status.
    slow = "double total(const double *d, int n){ (void)d; (void)n; volatile int spin = 1; while (spin) { } return 0; }"
    result = run_job(job({"a": read("sumtest_slow.c"), "b": slow}))

    assert result["status"] == "timeout"
    assert "бесконечн" in result["message"]


def test_unsupported_language_is_rejected():
    # "python" is no longer a valid example here (task 9 added it as a
    # supported language) — "rust" still pins the gate for languages that
    # remain genuinely unsupported.
    result = run_job(job({"a": "x", "b": "y"}) | {"lang": "rust"})

    assert result["status"] == "unsupported_lang"


def test_parse_output_handles_empty_stdout():
    payload, error = _parse_output("", expected_repeats=5)

    assert payload is None
    assert error


def test_parse_output_handles_unparseable_json():
    payload, error = _parse_output("this is not json", expected_repeats=5)

    assert payload is None
    assert error


def test_parse_output_handles_missing_check_keys():
    payload, error = _parse_output(
        '{"samples": [{"a": 1, "b": 1}], "check": {"a": 1}}', expected_repeats=1
    )

    assert payload is None
    assert error


def test_parse_output_handles_empty_samples():
    payload, error = _parse_output(
        '{"samples": [], "check": {"a": 1, "b": 1}}', expected_repeats=5
    )

    assert payload is None
    assert error


def test_parse_output_rejects_wrong_sample_count():
    # Pins the per-repeat invariant: a bench.c that silently dropped or
    # duplicated a repeat must be caught here, not produce a quietly wrong
    # median.
    payload, error = _parse_output(
        '{"samples": [{"a": 1, "b": 1}], "check": {"a": 1, "b": 1}}', expected_repeats=5
    )

    assert payload is None
    assert error


def test_parse_output_rejects_sample_missing_a_or_b():
    payload, error = _parse_output(
        '{"samples": [{"a": 1}], "check": {"a": 1, "b": 1}}', expected_repeats=1
    )

    assert payload is None
    assert error


def test_parse_output_accepts_well_formed_payload():
    payload, error = _parse_output(
        '{"samples": [{"a": 1.0, "b": 0.5}], "check": {"a": 1, "b": 1}}', expected_repeats=1
    )

    assert error is None
    assert payload["samples"] == [{"a": 1.0, "b": 0.5}]


def test_three_variant_output_requires_third_samples_and_check():
    import json
    payload = {'samples': [{'a': 1, 'b': 2, 'c': 3}], 'check': {'a': 7, 'b': 7, 'c': 7}}
    assert _parse_output(json.dumps(payload), 1, ('a', 'b', 'c'))[1] is None
    del payload['samples'][0]['c']
    assert _parse_output(json.dumps(payload), 1, ('a', 'b', 'c'))[1] is not None
    payload['samples'][0]['c'] = 3
    del payload['check']['c']
    assert _parse_output(json.dumps(payload), 1, ('a', 'b', 'c'))[1] is not None
