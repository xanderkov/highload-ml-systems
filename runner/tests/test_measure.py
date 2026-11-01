import pytest

from app.measure import ab_result, median, spread_pct, verdict


def test_median_of_odd_count():
    assert median([3.0, 1.0, 2.0]) == 2.0


def test_median_ignores_single_outlier():
    assert median([1.0, 1.0, 1.0, 1.0, 100.0]) == 1.0


def test_spread_pct_is_zero_for_identical_samples():
    assert spread_pct([5.0] * 11) == 0.0


def test_spread_pct_grows_with_noise():
    quiet = spread_pct([10.0, 10.1, 9.9, 10.0, 10.05, 9.95, 10.0, 10.02, 9.98, 10.01, 10.0])
    noisy = spread_pct([10.0, 14.0, 6.0, 12.0, 8.0, 11.0, 9.0, 13.0, 7.0, 10.0, 10.0])
    assert noisy > quiet


def test_ab_result_computes_speedup():
    samples = [{"a": 12.0, "b": 4.0} for _ in range(5)]

    result = ab_result(samples, {"a": 1.0, "b": 1.0}, tolerance=1e-9)

    assert result["baseline_ms"] == 12.0
    assert result["student_ms"] == 4.0
    assert result["speedup"] == pytest.approx(3.0)
    assert result["correct"] is True


def test_ab_result_marks_wrong_answer_incorrect_even_when_fast():
    samples = [{"a": 12.0, "b": 0.1} for _ in range(5)]

    result = ab_result(samples, {"a": 1.0, "b": 2.0}, tolerance=1e-9)

    assert result["speedup"] > 100
    assert result["correct"] is False


def test_ab_result_accepts_float_noise_within_tolerance():
    samples = [{"a": 12.0, "b": 4.0} for _ in range(5)]

    result = ab_result(samples, {"a": 1.0, "b": 1.0 + 1e-12}, tolerance=1e-9)

    assert result["correct"] is True


def test_ab_result_accepts_relatively_tiny_difference_on_large_values():
    samples = [{"a": 1.0, "b": 1.0}]

    result = ab_result(samples, {"a": 1e9, "b": 1e9 + 1e-3}, tolerance=1e-9)

    assert result["correct"] is True


def test_ab_result_rejects_relatively_large_difference_on_large_values():
    samples = [{"a": 1.0, "b": 1.0}]

    result = ab_result(samples, {"a": 1e9, "b": 1.1e9}, tolerance=1e-9)

    assert result["correct"] is False


def test_verdict_requires_both_correctness_and_target():
    target = {"metric": "speedup", "op": ">=", "value": 3.0}

    assert verdict({"speedup": 3.5}, True, target) is True
    assert verdict({"speedup": 3.5}, False, target) is False
    assert verdict({"speedup": 2.5}, True, target) is False


def test_verdict_rejects_unrecognized_op():
    target = {"metric": "speedup", "op": "==", "value": 3.0}

    with pytest.raises(ValueError, match="=="):
        verdict({"speedup": 3.0}, True, target)


def test_verdict_lower_is_better():
    target = {"metric": "pss_growth_ratio", "op": "<=", "value": 0.3}
    assert verdict({"speedup": 1.0, "pss_growth_ratio": 0.2}, True, target)
    assert not verdict({"speedup": 1.0, "pss_growth_ratio": 0.5}, True, target)


def test_verdict_speedup_unchanged():
    assert verdict({"speedup": 3.2}, True, {"metric": "speedup", "op": ">=", "value": 3})


def test_verdict_all_ops_at_boundary():
    values = {"speedup": 1.0, "m": 0.3}
    for op, expected in ((">=", True), (">", False), ("<=", True), ("<", False)):
        assert verdict(values, True, {"metric": "m", "op": op, "value": 0.3}) is expected


def test_verdict_missing_metric_raises_key_error():
    with pytest.raises(KeyError):
        verdict({"speedup": 1.0}, True, {"metric": "m", "op": "<=", "value": 1})
