from app.jobs import _prepare_python, run_job

HARNESS = "tests/fixtures/harness/pytest_sum"


def read(name):
    with open(f"tests/fixtures/snippets/{name}", encoding="utf-8") as handle:
        return handle.read()


def job(units, mode="exercise", target=None):
    return {
        "mode": mode,
        "lang": "python",
        "harness_dir": HARNESS,
        "units": units,
        "target": target or {"metric": "speedup", "op": ">=", "value": 10},
    }


def test_numpy_beats_python_loop():
    result = run_job(job({"a": read("pysum_slow.py"), "b": read("pysum_fast.py")}))

    assert result["status"] == "ok"
    assert result["correct"] is True
    assert result["passed"] is True
    # На Python-пути компиляции нет — сборка через build_c не запускается,
    # и compile_command не должен подхватить чужое значение с C-пути.
    assert result["compile_command"] is None


def test_python_syntax_error_is_reported():
    result = run_job(
        job({"a": read("pysum_slow.py"), "b": "def total(data)\n    return 1\n"})
    )

    assert result["status"] == "runtime_error"
    assert "SyntaxError" in result["log"]


def test_unsupported_language_still_rejected_alongside_python():
    # Добавление python не должно ослабить проверку: языки помимо c/python
    # обязаны по-прежнему отклоняться на входе, до чтения харнесса.
    result = run_job(job({"a": "x", "b": "y"}) | {"lang": "rust"})

    assert result["status"] == "unsupported_lang"


def test_prepare_python_env_is_minimal_with_omp_threads_pinned(tmp_path):
    # OMP_NUM_THREADS=1 — не опция, а требование: NumPy на OpenBLAS иначе
    # тихо уходит в многопоточность, и урок про память подменяется уроком
    # про число потоков с нестабильными числами от прогона к прогону.
    from pathlib import Path

    harness = Path(HARNESS)
    meta = {"warmup": 1, "repeats": 5, "sizes": [200000]}
    command, env = _prepare_python(tmp_path, harness, {}, meta)

    assert env["OMP_NUM_THREADS"] == "1"
    assert env["PYTHONPATH"] == str(tmp_path)
    assert env["BENCH_WARMUP"] == "1"
    assert env["BENCH_REPEATS"] == "5"
    assert env["BENCH_SIZES"] == "200000"
    assert "PATH" in env
    # Явный минимальный набор ключей — никакого случайного наследования
    # окружения runner-сервиса (в частности, никакого HOME/LD_* и т.п.).
    assert set(env.keys()) == {"PATH", "PYTHONPATH", "BENCH_WARMUP", "BENCH_REPEATS", "BENCH_SIZES", "OMP_NUM_THREADS"}


def test_threads_auto_leaves_omp_unset(tmp_path):
    from pathlib import Path

    _, env = _prepare_python(tmp_path, Path(HARNESS), {"a": "", "b": ""}, {"threads": "auto"})
    assert "OMP_NUM_THREADS" not in env


def test_threads_default_is_one(tmp_path):
    from pathlib import Path

    _, env = _prepare_python(tmp_path, Path(HARNESS), {"a": "", "b": ""}, {})
    assert env["OMP_NUM_THREADS"] == "1"


def test_shared_lib_is_copied(tmp_path):
    from pathlib import Path

    _prepare_python(tmp_path, Path(HARNESS), {"a": "", "b": ""}, {})
    assert (tmp_path / "helper.py").exists()


def test_invalid_threads_is_harness_error():
    result = run_job(
        job({"a": read("pysum_slow.py"), "b": read("pysum_fast.py")})
        | {"harness_dir": "tests/fixtures/harness/pytest_sum_badthreads"}
    )
    assert result["status"] == "harness_error"
    assert "threads" in result["message"]
    assert "4" in result["message"]


METRICS_HARNESS = "tests/fixtures/harness/metrics_echo"


def metrics_job(target, mode="exercise"):
    return {
        "mode": mode,
        "lang": "python",
        "harness_dir": METRICS_HARNESS,
        "units": {"a": "x = 1\n", "b": "x = 2\n"},
        "target": target,
    }


def test_missing_metric_is_output_error():
    result = run_job(job(
        {"a": read("pysum_slow.py"), "b": read("pysum_fast.py")},
        target={"metric": "pss_growth_ratio", "op": "<=", "value": 0.3},
    ))

    assert result["status"] == "output_error"
    assert result["message"] == "Харнесс не вернул метрику 'pss_growth_ratio' из цели задания"


def test_metrics_are_returned():
    result = run_job(metrics_job({"metric": "m", "op": "<=", "value": 1}))

    assert result["status"] == "ok"
    assert result["metrics"] == {"m": 0.5}
    assert result["baseline_metrics"] == {"m": 0.9}
    assert result["passed"] is True


def test_metric_target_not_met():
    result = run_job(metrics_job({"metric": "m", "op": "<=", "value": 0.4}))

    assert result["passed"] is False


def test_no_metrics_keys_without_harness_metrics():
    result = run_job(job({"a": read("pysum_slow.py"), "b": read("pysum_fast.py")}))

    assert "metrics" not in result and "baseline_metrics" not in result


def test_malformed_metrics_is_output_error(tmp_path):
    harness = tmp_path / "h"
    harness.mkdir()
    (harness / "meta.yml").write_text("kind: ab\nlang: python\nrepeats: 2\nwarmup: 0\n")
    (harness / "bench.py").write_text(
        "import json\n"
        "print(json.dumps({'samples': [{'a': 1.0, 'b': 1.0}] * 2, "
        "'check': {'a': 1.0, 'b': 1.0}, 'metrics': {'a': 5, 'b': {'m': 'x'}}}))\n"
    )
    result = run_job(metrics_job({"metric": "speedup", "op": ">=", "value": 1}) | {"harness_dir": str(harness)})

    assert result["status"] == "output_error"
    assert "metrics" in result["log"]
