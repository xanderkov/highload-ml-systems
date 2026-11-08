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
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

TRITON_URL = "http://triton:8000"
METRICS_URL = "http://triton:8002/metrics"
REPO = Path("/models")
# Вывод сервера (общий том triton_log): ошибки разбора config.pbtxt есть только там.
SERVER_LOG = Path("/triton-log/server.log")
_HERE = Path(__file__).resolve().parent
# Первый элемент входа, на котором model.py python backend отвечает ошибкой (глава 5).
BAD_INPUT = -1e9
READY_TIMEOUT_S = 60
UNLOAD_TIMEOUT_S = 30
# Прокси из окружения к серверу в сети compose не нужен и только мешает.
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))
# Строка name: верхнего уровня config.pbtxt: имя модели задаёт каталог.
_NAME_LINE = re.compile(r'^\s*name\s*:\s*"[^"]*"\s*$', re.MULTILINE)
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


class TritonUnavailable(RuntimeError):
    """Сервер Triton не отвечает."""


class TritonLoadError(RuntimeError):
    """Triton не загрузил модель; текст — сообщение сервера."""


def _call(method: str, path: str, body: bytes | None = None, *, base: str | None = None,
          timeout_s: float = 120) -> tuple[int, bytes]:
    url = (base or TRITON_URL) + path
    request = urllib.request.Request(url, data=body, method=method)
    try:
        with _NO_PROXY.open(request, timeout=timeout_s) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except OSError as exc:
        raise TritonUnavailable(
            f"сервер Triton недоступен ({url}): {exc}. Он поднимается вместе с курсом "
            f"(docker compose up); если только что запущен — подождите полминуты") from None


def _log_offset() -> int:
    try:
        return SERVER_LOG.stat().st_size
    except OSError:
        return 0


def _log_errors_since(offset: int, name: str) -> list[str]:
    """Строки ошибок из вывода сервера, записанные после offset и относящиеся к модели."""
    try:
        with SERVER_LOG.open("rb") as handle:
            handle.seek(offset)
            text = handle.read().decode(errors="replace")
    except OSError:
        return []
    lines = []
    for line in text.splitlines():
        # Формат glog/absl: E<дата> <время> <поток> <файл>:<строка>] сообщение.
        if not line.startswith("E"):
            continue
        message = line.split("] ", 1)[1] if "] " in line else line
        if name in message or "parsing" in message:
            lines.append(message.strip().strip('"'))
    return lines


def _error_text(raw: bytes) -> str:
    try:
        return json.loads(raw).get("error", raw.decode(errors="replace"))
    except (ValueError, AttributeError):
        return raw.decode(errors="replace")


def _index() -> list[dict]:
    status, raw = _call("POST", "/v2/repository/index", b"{}")
    if status != 200:
        raise TritonUnavailable(f"сервер Triton не отдал список моделей: HTTP {status} {_error_text(raw)}")
    return json.loads(raw)


def _unload_and_wait(names: set[str]) -> None:
    """Выгрузка асинхронна: ждём, пока модели не станут UNAVAILABLE (спека §7.1)."""
    for name in names:
        _call("POST", f"/v2/repository/models/{name}/unload", b"{}")
    deadline = time.monotonic() + UNLOAD_TIMEOUT_S
    while time.monotonic() < deadline:
        busy = {m["name"] for m in _index() if m["name"] in names and m.get("state") in ("READY", "LOADING", "UNLOADING")}
        if not busy:
            return
        time.sleep(0.1)


def _clean_repository() -> None:
    """Под server_lock других замеров нет: всё загруженное и записанное — остатки упавших."""
    _unload_and_wait({m["name"] for m in _index() if m.get("state") in ("READY", "LOADING", "UNLOADING")})
    for path in REPO.iterdir():
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)


@contextlib.contextmanager
def deploy(name: str, config: str, files: dict[str, bytes]):
    """Модель name на сервере на время блока; отдаёт базовый URL сервера.

    Вызывать под server_lock. Пишет REPO/name/config.pbtxt (строку name:
    убирает — имя задаёт каталог) и files (пути относительно REPO/name),
    загружает и ждёт готовности; на выходе выгружает и удаляет каталог.
    """
    _clean_repository()
    root = REPO / name
    try:
        root.mkdir(parents=True)
        (root / "config.pbtxt").write_text(_NAME_LINE.sub("", config), encoding="utf-8")
        for path, data in files.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        offset = _log_offset()
        status, raw = _call("POST", f"/v2/repository/models/{name}/load", b"{}")
        if status != 200:
            details = "\n".join(_log_errors_since(offset, name))
            raise TritonLoadError(f"Triton не загрузил модель: {_error_text(raw)}"
                                  + (f"\nСервер написал:\n{details}" if details else ""))
        deadline = time.monotonic() + READY_TIMEOUT_S
        while _call("GET", f"/v2/models/{name}/ready")[0] != 200:
            if time.monotonic() > deadline:
                raise TritonLoadError(f"модель не стала готовой за {READY_TIMEOUT_S} с")
            time.sleep(0.1)
        yield TRITON_URL
    finally:
        with contextlib.suppress(TritonUnavailable):
            _unload_and_wait({name})
        shutil.rmtree(root, ignore_errors=True)


def python_model_files() -> dict[str, bytes]:
    """Файлы версии 1 модели python backend: model.py и widemodel.py."""
    return {
        "1/model.py": (_HERE / "triton_model.py").read_bytes(),
        "1/widemodel.py": (_HERE / "widemodel.py").read_bytes(),
    }


def read_metrics() -> str:
    """Текст /metrics сервера (Prometheus)."""
    try:
        with _NO_PROXY.open(METRICS_URL, timeout=10) as response:
            return response.read().decode()
    except OSError as exc:
        raise TritonUnavailable(f"сервер Triton недоступен ({METRICS_URL}): {exc}") from None


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
