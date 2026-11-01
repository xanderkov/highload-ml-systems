import sys

from app.sandbox import run


def test_run_captures_stdout(tmp_path):
    result = run([sys.executable, "-c", "print('привет')"], tmp_path, timeout_s=10, memory_mb=512)

    assert result.returncode == 0
    assert result.stdout.strip() == "привет"
    assert result.timed_out is False


def test_run_captures_stderr_and_returncode(tmp_path):
    result = run(
        [sys.executable, "-c", "import sys; sys.stderr.write('плохо'); sys.exit(3)"],
        tmp_path,
        timeout_s=10,
        memory_mb=512,
    )

    assert result.returncode == 3
    assert "плохо" in result.stderr


def test_run_times_out(tmp_path):
    result = run(
        [sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, timeout_s=1, memory_mb=512
    )

    assert result.timed_out is True


def test_run_enforces_memory_limit(tmp_path):
    result = run(
        [sys.executable, "-c", "x = bytearray(400 * 1024 * 1024)"],
        tmp_path,
        timeout_s=20,
        memory_mb=128,
    )

    assert result.returncode != 0
    assert result.timed_out is False


def test_run_uses_given_cwd(tmp_path):
    (tmp_path / "marker.txt").write_text("тут")
    result = run(
        [sys.executable, "-c", "import pathlib; print(pathlib.Path('marker.txt').read_text())"],
        tmp_path,
        timeout_s=10,
        memory_mb=512,
    )

    assert "тут" in result.stdout


def test_run_does_not_execute_as_root(tmp_path):
    result = run(
        [sys.executable, "-c", "import os; print(os.getuid())"],
        tmp_path,
        timeout_s=10,
        memory_mb=512,
    )

    assert result.stdout.strip() != "0"
