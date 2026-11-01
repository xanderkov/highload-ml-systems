import statistics


def median(xs: list[float]) -> float:
    return float(statistics.median(xs))


def spread_pct(xs: list[float]) -> float:
    """Разброс замеров: (p90 - p10) / медиана, в процентах."""
    if len(xs) < 2:
        return 0.0
    ordered = sorted(xs)
    p10 = ordered[max(0, round(0.1 * (len(ordered) - 1)))]
    p90 = ordered[min(len(ordered) - 1, round(0.9 * (len(ordered) - 1)))]
    mid = median(xs)
    if mid == 0:
        return 0.0
    return (p90 - p10) / mid * 100.0


def _close(a: float, b: float, tolerance: float) -> bool:
    scale = max(abs(a), abs(b), 1.0)
    return abs(a - b) <= tolerance * scale


def ab_result(samples: list[dict], check: dict, tolerance: float) -> dict:
    a_times = [s["a"] for s in samples]
    b_times = [s["b"] for s in samples]
    baseline = median(a_times)
    student = median(b_times)
    return {
        "baseline_ms": baseline,
        "student_ms": student,
        "speedup": baseline / student if student > 0 else float("inf"),
        "spread_pct": max(spread_pct(a_times), spread_pct(b_times)),
        "correct": _close(float(check["a"]), float(check["b"]), tolerance),
    }


def verdict(speedup: float, correct: bool, target: dict) -> bool:
    if not correct:
        return False
    if target["metric"] != "speedup":
        raise ValueError(f"Неизвестная метрика цели: {target['metric']}")
    if target["op"] not in (">=", ">"):
        raise ValueError(f"Неизвестная операция сравнения: {target['op']}")
    value = float(target["value"])
    return speedup >= value if target["op"] == ">=" else speedup > value
