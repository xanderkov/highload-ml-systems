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


def _gone(pid):
    import os
    import time

    for _ in range(50):
        try:
            os.kill(pid, 0)
            with open(f"/proc/{pid}/stat") as stat:
                if stat.read().rsplit(")", 1)[1].split()[0] == "Z":
                    return True  # убит, ждёт только reap от init контейнера
        except (ProcessLookupError, FileNotFoundError):
            return True
        time.sleep(0.1)
    return False


FORKER = (
    "import os, sys, time\n"
    "pid = os.fork()\n"
    "if pid == 0:\n"
    "    time.sleep(1000)\n"
    "    os._exit(0)\n"
    "print(pid, flush=True)\n"
    "{tail}"
)


def test_timeout_kills_forked_children(tmp_path):
    result = run(
        [sys.executable, "-c", FORKER.format(tail="time.sleep(1000)\n")], tmp_path, timeout_s=2, memory_mb=512
    )

    assert result.timed_out is True
    assert _gone(int(result.stdout.split()[0]))


def test_background_grandchild_killed_after_normal_exit(tmp_path):
    result = run([sys.executable, "-c", FORKER.format(tail="")], tmp_path, timeout_s=2, memory_mb=512)

    assert result.timed_out is False
    assert result.returncode == 0
    assert _gone(int(result.stdout.split()[0]))


ESCAPER = (
    "import os, sys, time\n"
    "pid = os.fork()\n"
    "if pid == 0:\n"
    "    os.setsid()\n"  # своя сессия: killpg группы задания его не достанет
    "    time.sleep(60)\n"
    "    os._exit(0)\n"
    "print(pid, flush=True)\n"
)


def test_escaped_child_holding_pipe_does_not_hang(tmp_path):
    import os
    import signal
    import time

    started = time.monotonic()
    result = run([sys.executable, "-c", ESCAPER], tmp_path, timeout_s=1, memory_mb=512)
    elapsed = time.monotonic() - started
    try:
        os.kill(int(result.stdout.split()[0]), signal.SIGKILL)
    except (ProcessLookupError, ValueError, IndexError):
        pass

    assert elapsed < 20
    assert result.timed_out is False
    assert result.stdout.split()
