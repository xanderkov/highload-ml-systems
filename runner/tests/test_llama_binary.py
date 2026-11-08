"""llama-server в образе runner (make test-llm)."""
import json
import socket
import subprocess
import time
import urllib.request

import pytest

from app.sandbox import MAX_FILE_MB, _limits

pytestmark = pytest.mark.llm

SERVER = "/opt/llama/llama-server"
MODEL = "/opt/models/qwen05-q8.gguf"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_llama_server_runs_in_runner_image():
    proc = subprocess.run([SERVER, "--version"], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    assert "build 12199" in proc.stdout + proc.stderr


def test_llama_server_serves_under_sandbox_limits():
    port = _free_port()
    proc = subprocess.Popen(
        [SERVER, "-m", MODEL, "-t", "3", "-np", "16", "-c", "8192", "--host", "127.0.0.1",
         "--port", str(port), "--alias", "q"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, preexec_fn=_limits(2048, MAX_FILE_MB))
    try:
        deadline = time.monotonic() + 30
        while True:
            assert proc.poll() is None, proc.stderr.read().decode()[-3000:]
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                    if r.status == 200:
                        break
            except OSError:
                pass
            assert time.monotonic() < deadline, "llama-server не ответил на /health за 30 с"
            time.sleep(0.2)
        body = json.dumps({"model": "q", "prompt": "Hello", "max_tokens": 16, "temperature": 0,
                           "ignore_eos": True}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/completions", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            answer = json.load(r)
        assert answer["usage"]["completion_tokens"] == 16
    finally:
        proc.kill()
        proc.wait()
