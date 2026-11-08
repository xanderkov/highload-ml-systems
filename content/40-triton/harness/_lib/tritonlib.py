"""Triton из харнессов раздела «Triton»: протокол KServe v2, метрики, блокировка сервера.

Сервер один на всех (сервис triton в docker-compose), поэтому замеры идут под
файловой блокировкой server_lock: два параллельных замера на одном сервере
исказили бы друг друга. Модели харнесс кладёт в общий том /models и
загружает через HTTP API (--model-control-mode=explicit), см. deploy.

servicelib.py и widemodel.py в этом каталоге — побайтные копии из
30-naive-service/harness/_lib (_lib разделов независимы; равенство проверяет
web/tests/test_content.py).
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path

import numpy as np

REPO = Path("/models")
LOCK_PATH = str(REPO / ".lock")
INPUT_NAME = "INPUT__0"
OUTPUT_NAME = "OUTPUT__0"

# Имя метрики Prometheus → ключ словаря parse_metrics (сумма по версиям модели).
_MODEL_COUNTERS = {
    "nv_inference_request_success": "request_success",
    "nv_inference_request_failure": "request_failure",
    "nv_inference_count": "inference_count",
    "nv_inference_exec_count": "exec_count",
    "nv_inference_queue_duration_us": "queue_us",
    "nv_inference_compute_infer_duration_us": "compute_us",
}
_SAMPLE = re.compile(r'^(\w+)(?:\{([^}]*)\})?\s+(\S+)$')
_LABEL = re.compile(r'(\w+)="([^"]*)"')


class TritonBusy(RuntimeError):
    """Сервер занят другим замером дольше таймаута."""


def content_type(*, binary: bool = True) -> str:
    """Content-Type тела v2_body: бинарное расширение или чистый JSON."""
    return "application/octet-stream" if binary else "application/json"


def v2_body(array: np.ndarray, *, binary: bool = True, input_name: str = INPUT_NAME,
            output_name: str = OUTPUT_NAME) -> tuple[bytes, dict[str, str]]:
    """Тело запроса /v2/models/<name>/infer и его дополнительные заголовки.

    binary=True — binary tensor extension: JSON-заголовок, за ним сырые байты
    float32, длина заголовка — в Inference-Header-Content-Length. binary=False —
    тензор списком чисел в JSON (цена текстового протокола, глава 1). Выход
    всегда просим JSON-ом: в нём 10 чисел, бинарный выход ничего не экономит.
    """
    array = np.ascontiguousarray(array, dtype=np.float32)
    tensor = {"name": input_name, "shape": list(array.shape), "datatype": "FP32"}
    outputs = [{"name": output_name, "parameters": {"binary_data": False}}]
    if not binary:
        tensor["data"] = array.ravel().tolist()
        return json.dumps({"inputs": [tensor], "outputs": outputs}).encode(), {}
    tensor["parameters"] = {"binary_data_size": array.nbytes}
    header = json.dumps({"inputs": [tensor], "outputs": outputs}).encode()
    return header + array.tobytes(), {"Inference-Header-Content-Length": str(len(header))}


def parse_v2_response(raw: bytes) -> np.ndarray:
    """Первый выход JSON-ответа Triton как массив float32 своей формы."""
    output = json.loads(raw)["outputs"][0]
    return np.asarray(output["data"], dtype=np.float32).reshape(output["shape"])


def parse_metrics(text: str, model: str) -> dict[str, float]:
    """Счётчики модели из текста /metrics (сумма по версиям) и загрузка CPU сервера.

    rejected — отказы очереди (request_failure с reason="REJECTED").
    """
    result = {key: 0.0 for key in _MODEL_COUNTERS.values()}
    result.update(rejected=0.0, cpu_util=0.0)
    for line in text.splitlines():
        match = _SAMPLE.match(line.strip())
        if not match:
            continue
        name, labels, value = match.group(1), dict(_LABEL.findall(match.group(2) or "")), float(match.group(3))
        if name == "nv_cpu_utilization":
            result["cpu_util"] = value
        elif name in _MODEL_COUNTERS and labels.get("model") == model:
            result[_MODEL_COUNTERS[name]] += value
            if name == "nv_inference_request_failure" and labels.get("reason") == "REJECTED":
                result["rejected"] += value
    return result


def metrics_delta(before: dict[str, float], after: dict[str, float]) -> dict[str, float]:
    """Прирост счётчиков за замер; cpu_util — мгновенное значение, берётся из after."""
    delta = {key: after[key] - before.get(key, 0.0) for key in after}
    delta["cpu_util"] = after.get("cpu_util", 0.0)
    return delta


def mean_batch(delta: dict[str, float]) -> float:
    """Средний размер батча: элементов на один запуск модели."""
    return delta["inference_count"] / delta["exec_count"] if delta["exec_count"] else 0.0


def unique_name(prefix: str) -> str:
    """Имя модели на одно задание: повторный запуск не видит состояние прошлого."""
    return f"{prefix}-{os.getpid()}-{secrets.token_hex(3)}"


@contextlib.contextmanager
def server_lock(timeout_s: float = 120, path: str = LOCK_PATH):
    """Монопольный доступ к серверу Triton на время замера."""
    with open(path, "a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("сервер Triton занят другим замером, ждём…", file=sys.stderr, flush=True)
            deadline = time.monotonic() + timeout_s
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() > deadline:
                        raise TritonBusy(
                            f"сервер Triton занят другим замером дольше {timeout_s:.0f} с; "
                            f"дождитесь его окончания и запустите ещё раз") from None
                    time.sleep(0.1)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
