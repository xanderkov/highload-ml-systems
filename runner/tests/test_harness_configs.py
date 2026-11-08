"""Переписывание конфигов в харнессах раздела «Triton» (backpressure, instances_delay)."""
import importlib.util
import os
import sys

_root = os.environ.get("CONTENT_ROOT", "/content")
HARNESS = os.path.join(_root, "40-triton", "harness")
sys.path.insert(0, os.path.join(HARNESS, "_lib"))


def load(name):
    spec = importlib.util.spec_from_file_location(f"bench_{name}", os.path.join(HARNESS, name, "bench.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COLON_FORM = '''backend: "python"
max_batch_size: 4
instance_group [ { count: 1 kind: KIND_CPU } ]
parameters: { key: "TORCH_THREADS" value: { string_value: "3" } }
dynamic_batching: {
  default_queue_policy: { timeout_action: REJECT default_timeout_microseconds: 20000 }
}
'''


def test_size_limited_handles_colon_form():
    bench = load("backpressure")
    assert "max_queue_size: 8" in bench.size_limited(COLON_FORM)
    assert "default_queue_policy" not in bench.unbounded(COLON_FORM)


def test_make_config_handles_colon_form():
    bench = load("instances_delay")
    config = bench.make_config(COLON_FORM, 2, 1, 5)
    assert "max_queue_delay_microseconds: 5000" in config
    assert "count: 2" in config
    assert 'string_value: "1"' in config
