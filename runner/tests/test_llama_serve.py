"""llama.serve раздела «LLM» против настоящего llama-server (make test-llm)."""
import os
import sys

import pytest

_root = os.environ.get("CONTENT_ROOT", "/content")
sys.path.insert(0, os.path.join(_root, "50-llm", "harness", "_lib"))

import llama  # noqa: E402
import llmload  # noqa: E402
import stand  # noqa: E402

pytestmark = pytest.mark.llm


def no_llama_left() -> bool:
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as handle:
                if b"llama-server" in handle.read():
                    return False
        except OSError:
            continue
    return True


def test_serve_answers_completion():
    load_cpu, service = stand.cpus()
    with llama.serve(slots=4, ctx_total=2048, cpus=service) as url:
        result = llmload.run_http(url, llama.MODEL, rps=2, duration_s=2, mix=llmload.Mix(),
                                  load_cpu=load_cpu)
    assert result.errors() == 0, result.first_error()
    assert result.truncated() == 0
    assert all(rec.n_tokens == rec.max_new for rec in result.per_request)
    assert no_llama_left()


def test_bad_args_raise_with_stderr():
    _, service = stand.cpus()
    with pytest.raises(llama.LlamaStartError) as err:
        with llama.serve(slots=4, ctx_total=2048, cpus=service, extra=["--no-such-flag"]):
            pass
    assert "no-such-flag" in str(err.value)
    assert no_llama_left()


def test_serve_works_without_library_path(monkeypatch):
    # runner запускает харнесс с минимальным окружением, без LD_LIBRARY_PATH.
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    _, service = stand.cpus()
    with llama.serve(slots=2, ctx_total=512, cpus=service) as url:
        assert url.startswith("http://127.0.0.1:")


_OVERLOAD = """
import sys
sys.path[:0] = ["/app", {lib!r}]
from app.sandbox import _limits
_limits(2048)()
import llama, llmload, stand

if __name__ == "__main__":
    load_cpu, service = stand.cpus()
    with llama.serve(slots=1, ctx_total=256, cpus=service) as url:
        r = llmload.run_http(url, llama.MODEL, rps=8, duration_s=5, mix=llmload.Mix(), load_cpu=load_cpu)
    print("errors", r.errors(), r.first_error())
"""


def test_queue_of_requests_under_sandbox_limits(tmp_path):
    # Под RLIMIT_AS задания очередь из десятков соединений роняла сервер:
    # пул HTTP-потоков не мог создать поток (арены malloc), запросы — без ответа.
    import subprocess
    lib = os.path.join(_root, "50-llm", "harness", "_lib")
    script = tmp_path / "overload.py"
    script.write_text(_OVERLOAD.format(lib=lib))
    proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=120, cwd=tmp_path)
    assert "errors 0 None" in proc.stdout, proc.stdout + proc.stderr[-2000:]


_HANG = """
import sys, time
sys.path.insert(0, {lib!r})
import llama, stand

if __name__ == "__main__":
    _, service = stand.cpus()
    with llama.serve(slots=2, ctx_total=512, cpus=service):
        print("up", flush=True)
        time.sleep(600)
"""


def test_runner_timeout_does_not_leave_llama_running(tmp_path):
    # Таймаут задания: runner убивает группу процессов харнесса (SIGKILL),
    # finally в serve() не выполняется — сервер не должен пережить харнесс.
    from app.sandbox import run
    lib = os.path.join(_root, "50-llm", "harness", "_lib")
    (tmp_path / "hang.py").write_text(_HANG.format(lib=lib))
    result = run([sys.executable, "hang.py"], tmp_path, timeout_s=8, memory_mb=2048)
    assert result.timed_out and "up" in result.stdout, result
    import time
    time.sleep(1)
    assert no_llama_left()
