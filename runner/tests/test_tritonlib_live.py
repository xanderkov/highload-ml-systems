"""tritonlib против живого сервера triton (make test-triton)."""
import json
import os
import sys
import threading
import urllib.error
import urllib.request

import numpy as np
import pytest
import torch

_root = os.environ.get("CONTENT_ROOT", "/content")
sys.path.insert(0, os.path.join(_root, "40-triton", "harness", "_lib"))

import tritonlib  # noqa: E402
import widemodel  # noqa: E402

pytestmark = pytest.mark.triton

CONFIG = """
backend: "python"
max_batch_size: 32
input [ { name: "INPUT__0" data_type: TYPE_FP32 dims: [ 3, 64, 64 ] } ]
output [ { name: "OUTPUT__0" data_type: TYPE_FP32 dims: [ 10 ] } ]
instance_group [ { count: 1 kind: KIND_CPU } ]
parameters: { key: "TORCH_THREADS" value: { string_value: "1" } }
"""
NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def post(url: str, body: bytes, headers: dict) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with NO_PROXY.open(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def infer(base: str, name: str, x: np.ndarray) -> tuple[int, bytes]:
    body, headers = tritonlib.v2_body(x)
    return post(f"{base}/v2/models/{name}/infer", body, {**headers, "Content-Type": tritonlib.content_type()})


def index() -> list[dict]:
    return json.loads(post(f"{tritonlib.TRITON_URL}/v2/repository/index", b"{}", {})[1])


def loaded() -> set[str]:
    return {m["name"] for m in index() if m.get("state") == "READY"}


@pytest.fixture
def x():
    return np.random.default_rng(0).standard_normal((3, 3, 64, 64), dtype=np.float32)


def expected(x):
    with torch.inference_mode():
        return widemodel.make_model()(torch.from_numpy(x)).numpy()


def test_deploy_loads_and_answers(x):
    name = tritonlib.unique_name("t")
    with tritonlib.server_lock(), tritonlib.deploy(name, CONFIG, tritonlib.python_model_files()) as base:
        status, raw = infer(base, name, x)
    assert status == 200, raw
    assert np.allclose(tritonlib.parse_v2_response(raw), expected(x), rtol=1e-4, atol=1e-4)


def test_deploy_unloads_on_exit():
    name = tritonlib.unique_name("t")
    with tritonlib.server_lock(), tritonlib.deploy(name, CONFIG, tritonlib.python_model_files()):
        assert name in loaded()
    assert name not in loaded()
    assert not (tritonlib.REPO / name).exists()


def test_deploy_strips_name_from_config():
    # Имя модели — по каталогу; чужое имя в конфиге студента не должно мешать загрузке.
    name = tritonlib.unique_name("t")
    with tritonlib.server_lock(), tritonlib.deploy(name, 'name: "whatever"\n' + CONFIG, tritonlib.python_model_files()):
        assert name in loaded()


def test_broken_config_raises_load_error_with_triton_text():
    name = tritonlib.unique_name("t")
    with tritonlib.server_lock(), pytest.raises(tritonlib.TritonLoadError) as info:
        with tritonlib.deploy(name, CONFIG + "\nno_such_field: 1\n", tritonlib.python_model_files()):
            pass
    assert "no_such_field" in str(info.value)
    assert name not in loaded()


def test_stale_model_unloaded_before_deploy():
    stale = tritonlib.unique_name("stale")
    (tritonlib.REPO / stale / "1").mkdir(parents=True)
    (tritonlib.REPO / stale / "config.pbtxt").write_text(CONFIG)
    for path, data in tritonlib.python_model_files().items():
        (tritonlib.REPO / stale / path).write_bytes(data)
    status, raw = post(f"{tritonlib.TRITON_URL}/v2/repository/models/{stale}/load", b"{}", {})
    assert status == 200, raw
    name = tritonlib.unique_name("t")
    with tritonlib.server_lock(), tritonlib.deploy(name, CONFIG, tritonlib.python_model_files()):
        assert loaded() == {name}
        assert not (tritonlib.REPO / stale).exists()


def test_unavailable_server_message(monkeypatch):
    monkeypatch.setattr(tritonlib, "TRITON_URL", "http://127.0.0.1:9")
    with pytest.raises(tritonlib.TritonUnavailable, match="сервер Triton недоступен"):
        with tritonlib.deploy(tritonlib.unique_name("t"), CONFIG, tritonlib.python_model_files()):
            pass


def test_bad_input_fails_only_its_request():
    name = tritonlib.unique_name("t")
    config = CONFIG + "dynamic_batching { max_queue_delay_microseconds: 200000 }\n"
    good = np.zeros((1, 3, 64, 64), dtype=np.float32)
    bad = good.copy()
    bad.flat[0] = tritonlib.BAD_INPUT
    results = {}
    with tritonlib.server_lock(), tritonlib.deploy(name, config, tritonlib.python_model_files()) as base:
        before = tritonlib.parse_metrics(tritonlib.read_metrics(), name)
        threads = [threading.Thread(target=lambda k=k, v=v: results.__setitem__(k, infer(base, name, v)))
                   for k, v in enumerate([good, bad, good, good])]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        delta = tritonlib.metrics_delta(before, tritonlib.parse_metrics(tritonlib.read_metrics(), name))
    assert [results[k][0] for k in range(4)] == [200, 400, 200, 200], results
    assert delta["exec_count"] < 4  # запросы действительно собрались в батч


def test_infer_returns_output_for_batch(x):
    name = tritonlib.unique_name("t")
    with tritonlib.server_lock(), tritonlib.deploy(name, CONFIG, tritonlib.python_model_files()):
        out = tritonlib.infer(name, x)
    assert out.shape == (3, 10)
    assert np.allclose(out, expected(x), rtol=1e-4, atol=1e-4)


def test_infer_error_carries_server_message():
    name = tritonlib.unique_name("t")
    bad = np.zeros((1, 3, 64, 64), dtype=np.float32)
    bad.flat[0] = tritonlib.BAD_INPUT
    with tritonlib.server_lock(), tritonlib.deploy(name, CONFIG, tritonlib.python_model_files()):
        with pytest.raises(tritonlib.TritonInferError, match="битый вход"):
            tritonlib.infer(name, bad)
