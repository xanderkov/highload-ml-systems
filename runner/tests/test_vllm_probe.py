"""Проба сервиса vllm: не запущен / грузится / готов."""
import http.server
import os
import sys
import threading

import pytest

_root = os.environ.get("CONTENT_ROOT", "/content")
sys.path.insert(0, os.path.join(_root, "50-llm", "harness", "_lib"))

import vllmprobe  # noqa: E402


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        code = self.server.health if self.path == "/health" else 200
        self.send_response(code)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")


@pytest.fixture
def server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()


def test_absent_when_nothing_listens():
    assert vllmprobe.probe("http://127.0.0.1:9", timeout_s=1) == "absent"


def test_absent_when_name_does_not_resolve():
    assert vllmprobe.probe("http://no-such-host.invalid:8000", timeout_s=1) == "absent"


def test_loading_while_health_is_not_ok(server):
    server.health = 503
    assert vllmprobe.probe(f"http://127.0.0.1:{server.server_address[1]}", timeout_s=1) == "loading"


def test_ready_when_health_ok(server):
    server.health = 200
    assert vllmprobe.probe(f"http://127.0.0.1:{server.server_address[1]}", timeout_s=1) == "ready"
