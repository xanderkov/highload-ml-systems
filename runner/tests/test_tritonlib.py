"""tritonlib раздела «Triton»: протокол KServe v2, метрики, блокировка сервера.

Здесь — части, которым сервер не нужен; работа с живым Triton —
в test_tritonlib_live.py (маркер triton).
"""
import json
import os
import subprocess
import sys
import textwrap
import time

import numpy as np
import pytest

_root = os.environ.get("CONTENT_ROOT", "/content")
LIB = os.path.join(_root, "40-triton", "harness", "_lib")
sys.path.insert(0, LIB)

import tritonlib  # noqa: E402

METRICS = textwrap.dedent("""\
    # HELP nv_inference_request_success Number of successful inference requests
    # TYPE nv_inference_request_success counter
    nv_inference_request_success{model="m",version="1"} 10
    nv_inference_request_success{model="m",version="2"} 5
    nv_inference_request_success{model="other",version="1"} 999
    nv_inference_request_failure{model="m",reason="REJECTED",version="1"} 3
    nv_inference_request_failure{model="m",reason="BACKEND",version="1"} 1
    nv_inference_count{model="m",version="1"} 40
    nv_inference_exec_count{model="m",version="1"} 4
    nv_inference_queue_duration_us{model="m",version="1"} 1500
    nv_inference_compute_infer_duration_us{model="m",version="1"} 8000
    nv_inference_request_duration_us{model="m",version="1"} 12000
    nv_cpu_utilization 0.25
""")


def test_v2_body_binary_layout():
    x = np.arange(2 * 3 * 64 * 64, dtype=np.float32).reshape(2, 3, 64, 64)
    body, headers = tritonlib.v2_body(x)
    length = int(headers["Inference-Header-Content-Length"])
    header = json.loads(body[:length])
    assert header["inputs"] == [{"name": "INPUT__0", "shape": [2, 3, 64, 64], "datatype": "FP32",
                                 "parameters": {"binary_data_size": x.nbytes}}]
    assert header["outputs"] == [{"name": "OUTPUT__0", "parameters": {"binary_data": False}}]
    assert body[length:] == x.tobytes()


def test_v2_body_json():
    x = np.ones((1, 3, 64, 64), dtype=np.float32)
    body, headers = tritonlib.v2_body(x, binary=False)
    assert headers == {}
    header = json.loads(body)
    assert header["inputs"][0]["shape"] == [1, 3, 64, 64]
    assert header["inputs"][0]["data"] == [1.0] * x.size
    assert "parameters" not in header["inputs"][0]


def test_v2_body_content_types():
    assert tritonlib.content_type(binary=True) == "application/octet-stream"
    assert tritonlib.content_type(binary=False) == "application/json"


def test_parse_v2_response():
    raw = json.dumps({"model_name": "m", "outputs": [
        {"name": "OUTPUT__0", "datatype": "FP32", "shape": [2, 3], "data": [1, 2, 3, 4, 5, 6]}]}).encode()
    out = tritonlib.parse_v2_response(raw)
    assert out.dtype == np.float32
    assert out.shape == (2, 3)
    assert out[1, 2] == 6


def test_parse_metrics_sums_versions_and_ignores_other_models():
    m = tritonlib.parse_metrics(METRICS, "m")
    assert m["request_success"] == 15
    assert m["request_failure"] == 4
    assert m["rejected"] == 3
    assert m["inference_count"] == 40
    assert m["exec_count"] == 4
    assert m["queue_us"] == 1500
    assert m["compute_us"] == 8000
    assert m["request_us"] == 12000
    assert m["cpu_util"] == 0.25


def test_parse_metrics_missing_model_is_zeros():
    m = tritonlib.parse_metrics(METRICS, "absent")
    assert m["request_success"] == 0
    assert m["exec_count"] == 0


def test_metrics_delta_and_mean_batch():
    before = tritonlib.parse_metrics(METRICS, "m")
    after = dict(before, inference_count=before["inference_count"] + 64, exec_count=before["exec_count"] + 4)
    delta = tritonlib.metrics_delta(before, after)
    assert delta["inference_count"] == 64
    assert tritonlib.mean_batch(delta) == 16
    assert tritonlib.mean_batch({"inference_count": 0, "exec_count": 0}) == 0


def test_unique_name_differs_and_is_valid():
    a, b = tritonlib.unique_name("hook"), tritonlib.unique_name("hook")
    assert a != b
    assert a.startswith("hook-")
    assert all(c.isalnum() or c in "-_" for c in a)


def test_server_lock_second_holder_waits(tmp_path):
    lock = tmp_path / ".lock"
    holder = subprocess.Popen([sys.executable, "-c", textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {LIB!r})
        import tritonlib
        with tritonlib.server_lock(path={str(lock)!r}):
            print("held", flush=True)
            time.sleep(1.0)
    """)], stdout=subprocess.PIPE, text=True)
    assert holder.stdout.readline().strip() == "held"
    started = time.perf_counter()
    waiter = subprocess.run([sys.executable, "-c", textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {LIB!r})
        import tritonlib
        with tritonlib.server_lock(path={str(lock)!r}):
            pass
    """)], capture_output=True, text=True, timeout=30)
    waited = time.perf_counter() - started
    holder.wait(timeout=10)
    assert waiter.returncode == 0, waiter.stderr
    assert waited > 0.5
    assert "занят другим замером" in waiter.stderr


def test_server_lock_times_out(tmp_path):
    lock = tmp_path / ".lock"
    with tritonlib.server_lock(path=str(lock)):
        holder = subprocess.run([sys.executable, "-c", textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {LIB!r})
            import tritonlib
            try:
                with tritonlib.server_lock(path={str(lock)!r}, timeout_s=0.3):
                    pass
            except tritonlib.TritonBusy as exc:
                print("busy", exc)
        """)], capture_output=True, text=True, timeout=30)
    assert holder.stdout.startswith("busy")


GOOD_CONFIG = {
    "max_batch_size": 32,
    "input": [{"name": "INPUT__0", "data_type": "TYPE_FP32", "dims": ["3", "64", "64"]}],
    "output": [{"name": "OUTPUT__0", "data_type": "TYPE_FP32", "dims": ["10"]}],
}


def test_io_problem_accepts_stand_config():
    assert tritonlib.io_problem(GOOD_CONFIG) is None


def test_io_problem_zero_batch():
    assert "max_batch_size" in tritonlib.io_problem(dict(GOOD_CONFIG, max_batch_size=0))


def test_io_problem_wrong_input_name():
    config = dict(GOOD_CONFIG, input=[{"name": "input", "data_type": "TYPE_FP32", "dims": ["3", "64", "64"]}])
    problem = tritonlib.io_problem(config)
    assert "INPUT__0" in problem and "input TYPE_FP32" in problem


def test_log_errors_since_survives_truncated_log(tmp_path, monkeypatch):
    # Сервер обрезает свой лог, когда тот растёт; старое смещение тогда больше файла.
    log = tmp_path / "server.log"
    log.write_text('E1108 05:58:54.272044 1 x.cc:1] "Poll failed for model directory \'m-1\': bad"\n')
    monkeypatch.setattr(tritonlib, "SERVER_LOG", log)
    assert tritonlib._log_errors_since(10_000, "m-1") == ["Poll failed for model directory 'm-1': bad"]


MULTILINE_CONFIG = '''name: "student"
backend: "python"
max_batch_size: 32

input [
  {
    name: "INPUT__0"
    data_type: TYPE_FP32
    dims: [ 3, 64, 64 ]
  }
]
output [ { name: "OUTPUT__0" data_type: TYPE_FP32 dims: [ 10 ] } ]
'''


def test_strip_model_name_keeps_nested_names_and_line_numbers():
    stripped = tritonlib.strip_model_name(MULTILINE_CONFIG)
    lines = stripped.split("\n")
    assert lines[0].strip() == ""
    assert '    name: "INPUT__0"' in lines
    assert len(lines) == len(MULTILINE_CONFIG.split("\n"))


def test_strip_model_name_ignores_comments_and_strings():
    config = '# name: "x" { [\nparameters: { key: "a{" value: { string_value: "}" } }\nname: "m"\n'
    stripped = tritonlib.strip_model_name(config)
    assert 'name: "m"' not in stripped
    assert stripped.startswith('# name: "x" { [')


def test_server_lock_is_reentrant(tmp_path):
    lock = str(tmp_path / ".lock")
    with tritonlib.server_lock(path=lock):
        with tritonlib.server_lock(path=lock, timeout_s=0.2):
            pass


def test_io_problem_caps_instances():
    config = dict(GOOD_CONFIG, instance_group=[{"count": 20, "kind": "KIND_CPU"}])
    assert "count" in tritonlib.io_problem(config)
