"""Сервис triton из docker-compose: живой и видит общий репозиторий моделей.

Маркер triton: тесты требуют поднятого сервиса (make test-triton).
"""
import os
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.triton

TRITON_URL = os.environ.get("TRITON_URL", "http://triton:8000")


def test_triton_is_live():
    with urllib.request.urlopen(f"{TRITON_URL}/v2/health/live", timeout=10) as response:
        assert response.status == 200


def test_model_repo_writable():
    probe = Path("/models") / f".probe-{os.getpid()}"
    probe.write_text("ok")
    assert probe.read_text() == "ok"
    probe.unlink()
