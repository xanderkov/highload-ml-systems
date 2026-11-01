import os
import sys

import torch

_root = os.environ.get("CONTENT_ROOT", "/content")
sys.path.insert(0, os.path.join(_root, "20-python-runtime", "harness", "_lib"))

import memlib  # noqa: E402
import tinymodel  # noqa: E402


def test_pss_grows_after_allocation():
    before = memlib.pss_mib()
    data = bytearray(64 * 1024 * 1024)
    data[::4096] = b"x" * len(data[::4096])  # touch every page
    assert memlib.pss_mib() - before > 50
    del data


def test_rss_grows_after_allocation():
    before = memlib.rss_mib()
    data = bytearray(64 * 1024 * 1024)
    data[::4096] = b"x" * len(data[::4096])
    assert memlib.rss_mib() - before > 50
    del data


def test_pss_of_explicit_pid():
    assert memlib.pss_mib(os.getpid()) > 0
    assert memlib.rss_mib(os.getpid()) > 0


def test_tinymodel_is_deterministic():
    x = tinymodel.make_input(2)
    assert x.shape == (2, 3, 64, 64)
    with torch.no_grad():
        assert torch.equal(tinymodel.make_model()(x), tinymodel.make_model()(x))
