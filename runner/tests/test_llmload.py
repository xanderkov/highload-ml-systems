"""llmload раздела «LLM»: процесс-движок, стриминговый HTTP-клиент, подсчёт goodput."""
import http.server
import json
import os
import sys
import threading
import time

import pytest

_root = os.environ.get("CONTENT_ROOT", "/content")
sys.path.insert(0, os.path.join(_root, "50-llm", "harness", "_lib"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "fixtures"))

import engine_crash  # noqa: E402
import engine_overflow  # noqa: E402
import engine_ref  # noqa: E402
import engine_stall  # noqa: E402
import llmload  # noqa: E402
import stand  # noqa: E402
import tinygpt  # noqa: E402


def cpus():
    load_cpu, service = stand.cpus()
    return dict(service_cpus=service, load_cpu=load_cpu)


def test_engine_tokens_match_alone():
    mix = llmload.Mix(short=4, long=12)
    result = llmload.run_engine(engine_ref.engine, model_seed=0, max_batch=8, rps=4, duration_s=2,
                                mix=mix, **cpus())
    assert result.errors() == 0
    assert len(result.per_request) == 8
    model = tinygpt.make_model(seed=0)
    for rec in result.per_request:
        assert rec.tokens == tinygpt.generate_alone(model, rec.prompt, rec.max_new)
        assert rec.n_tokens == rec.max_new
        assert rec.ttft_s is not None and rec.ttft_s <= rec.e2e_s
        assert len(rec.itl_s) == rec.max_new - 1
    assert {rec.cls for rec in result.per_request} <= {"short", "long"}


def test_stalled_engine_is_reported():
    t0 = time.monotonic()
    with pytest.raises(llmload.EngineStalled) as err:
        llmload.run_engine(engine_stall.engine, model_seed=0, max_batch=4, rps=4, duration_s=1,
                           mix=llmload.Mix(), stall_s=3, **cpus())
    assert time.monotonic() - t0 <= 3 + 1 + 15  # прогон 1 с + stall + запуск процесса
    assert "не пришло ни одного токена" in str(err.value)
    with pytest.raises(ProcessLookupError):
        os.kill(err.value.pid, 0)


def test_crashing_engine_shows_traceback():
    with pytest.raises(llmload.EngineCrashed) as err:
        llmload.run_engine(engine_crash.engine, model_seed=0, max_batch=4, rps=4, duration_s=1,
                           mix=llmload.Mix(), **cpus())
    assert "ValueError: boom" in str(err.value)
    assert "engine_crash.py" in str(err.value)


def test_sending_after_done_is_reported():
    with pytest.raises(llmload.EngineCrashed) as err:
        llmload.run_engine(engine_overflow.engine, model_seed=0, max_batch=4, rps=4, duration_s=1,
                           mix=llmload.Mix(), **cpus())
    assert "уже получил все" in str(err.value)


class _SSE(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        if self.server.fail:
            self.send_response(500)
            self.send_header("Content-Length", "4")
            self.end_headers()
            self.wfile.write(b"oops")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for word in ("a", "b", "c"):
            chunk = {"choices": [{"text": word, "finish_reason": None}]}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.flush()
            time.sleep(0.01)
        done = {"choices": [{"text": "", "finish_reason": "length"}]}
        self.wfile.write(f"data: {json.dumps(done)}\n\ndata: [DONE]\n\n".encode())


@pytest.fixture(params=[False, True], ids=["ok", "500"])
def sse_server(request):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SSE)
    server.fail = request.param
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


def test_sse_parsing(sse_server):
    url = f"http://127.0.0.1:{sse_server.server_address[1]}"
    result = llmload.run_http(url, "q", rps=4, duration_s=1, mix=llmload.Mix(short=3, long=3),
                              load_cpu=cpus()["load_cpu"])
    assert len(result.per_request) == 4
    for rec in result.per_request:
        if sse_server.fail:
            assert "500" in rec.error
        else:
            assert rec.error is None
            assert rec.n_tokens == 3
            assert rec.ttft_s is not None


def rec(cls="short", max_new=16, n=16, ttft=0.1, error=None):
    return llmload.Rec(cls=cls, prompt=[1], max_new=max_new, ttft_s=ttft, e2e_s=1.0, tokens=None,
                       n_tokens=n, itl_s=[], error=error)


def test_goodput_counts_truncated_as_bad():
    result = llmload.Result([rec(), rec(n=10), rec(error="boom"), rec(ttft=0.9)], duration_s=2.0)
    assert result.truncated() == 1
    assert result.errors() == 1
    assert result.goodput(ttft_slo_s=0.5) == pytest.approx(0.5)  # 1 хороший за 2 с
