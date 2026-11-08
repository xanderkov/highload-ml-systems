"""Общий стенд замеров раздела «Triton»: входы, тела запросов, нагрузка, проверка ответов.

Стенд тот же, что в разделе 30: генератор нагрузки (servicelib.run_load) на
CPU 0, сервису — 3 CPU. Сервер Triton прибит к своим 3 CPU в docker-compose
(TRITON_CPUS, по умолчанию 1-3 — те же, что получает сервис раздела 30 через
servicelib.service_cpus), поэтому сравнение Triton с сервисом раздела 30
идёт на одинаковых CPU.
"""
from __future__ import annotations

import contextlib
import gc
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

import servicelib
import tritonlib
import widemodel

HERE = Path(__file__).resolve().parent
INPUTS = 64
OCTET = "application/octet-stream"


def block_config() -> str:
    """Конфиг из блока замера: правка студента (unit_b), иначе исходный (unit_a)."""
    for name in ("unit_b.pbtxt", "unit_a.pbtxt"):
        if Path(name).exists():
            return Path(name).read_text(encoding="utf-8")
    fail("харнессу не передан config.pbtxt")


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(1)


@dataclass
class Inputs:
    """INPUTS входов по одному изображению и выход widemodel на каждом (эталон ответов)."""
    arrays: list[np.ndarray]
    expected: np.ndarray

    @classmethod
    def make(cls, seed: int = 1) -> "Inputs":
        torch.manual_seed(seed)
        x = torch.randn(INPUTS, 3, 64, 64)
        torch.set_num_threads(1)
        with torch.inference_mode():
            expected = widemodel.make_model()(x).numpy()
        return cls([a[None] for a in x.numpy()], expected)


@dataclass
class Target:
    """Куда и как слать запросы: адрес, путь, тела по кругу, заголовки, парсер ответа."""
    url: str
    path: str
    bodies: list[bytes]
    content_type: str
    headers: dict[str, str]
    parse: callable

    def body(self, i: int) -> bytes:
        return self.bodies[i % len(self.bodies)]

    def wrong(self, responses: list, inputs: Inputs) -> int:
        """Ответов, не совпавших с выходом модели для своего входа (None — ошибка, не считается)."""
        wrong = 0
        for i, raw in enumerate(responses):
            if raw is None:
                continue
            try:
                got = self.parse(raw).reshape(-1)
            except (ValueError, KeyError, IndexError, TypeError):
                wrong += 1
                continue
            want = inputs.expected[i % len(inputs.arrays)]
            if got.shape != want.shape or not np.allclose(got, want, rtol=1e-4, atol=1e-4):
                wrong += 1
        return wrong


def by_address(url: str) -> str:
    """URL с IP вместо имени хоста.

    asyncio.open_connection по имени зовёт getaddrinfo в пуле потоков на
    каждое новое соединение. Под перегрузкой соединений тысячи, потоки и их
    арены malloc упираются в лимит памяти задания (RLIMIT_AS) — генератор
    падает с MemoryError. Имя сервера резолвим один раз.
    """
    scheme, rest = url.split("://", 1)
    host, port = rest.rstrip("/").rsplit(":", 1)
    return f"{scheme}://{socket.gethostbyname(host)}:{port}"


def triton_target(url: str, name: str, inputs: Inputs, *, binary: bool = True) -> Target:
    url = by_address(url)
    pairs = [tritonlib.v2_body(a, binary=binary) for a in inputs.arrays]
    # Форма у всех входов одна, поэтому и длина JSON-заголовка одна на все тела.
    return Target(url, f"/v2/models/{name}/infer", [b for b, _ in pairs], tritonlib.content_type(binary=binary),
                  pairs[0][1], tritonlib.parse_v2_response)


def service30_target(url: str, inputs: Inputs) -> Target:
    """Сервис раздела 30 (batcher_app): 12 288 float32 на вход, 10 float32 в ответ."""
    return Target(url, "/predict", [a.astype(np.float32).tobytes() for a in inputs.arrays], OCTET, {},
                  lambda raw: np.frombuffer(raw, dtype=np.float32))


@contextlib.contextmanager
def service30(batcher_module: str, cpus: set[int], *, max_batch_size: int = 32, max_delay_s: float = 0.005,
              torch_threads: int = 3):
    """Сервис раздела 30 с батчером batcher_module (batcher_starter — батч из одного)."""
    env = {"BATCHER_MODULE": batcher_module, "MAX_BATCH_SIZE": str(max_batch_size), "MAX_DELAY_S": str(max_delay_s)}
    with servicelib.start_service(str(HERE / "batcher_app.py"), workers=1, torch_threads=torch_threads,
                                  cpus=cpus, env=env) as url:
        yield url


def load(target: Target, rps: float, duration_s: float, cpus: set[int], *, timeout_s: float = 10):
    """Открытая нагрузка; разовое отставание генератора (соседние процессы) — один повтор."""
    kwargs = dict(path=target.path, rps=rps, duration_s=duration_s, make_body=target.body,
                  content_type=target.content_type, cpus=cpus, timeout_s=timeout_s, headers=target.headers)
    # Циклический сборщик мусора на время замера выключен: под перегрузкой у
    # генератора сотни ожидающих соединений и задач, и полный проход сборщика
    # останавливал event loop на десятки миллисекунд — генератор отставал от
    # расписания (в нашем замере 3 запуска задания из 5 на стартовом конфиге).
    gc.disable()
    try:
        return servicelib.run_load(target.url, **kwargs)
    except servicelib.LoadGeneratorLagging:
        try:
            return servicelib.run_load(target.url, **kwargs)
        except servicelib.LoadGeneratorLagging as exc:
            fail(f"генератор нагрузки не успел отправить запросы по расписанию ({rps:.0f} RPS, "
                 f"{duration_s:.1f} с) — скорее всего, машина занята другими процессами; "
                 f"запустите ещё раз ({exc})")
    finally:
        gc.enable()


def capacity(target: Target, cpus: set[int], *, connections: int = 8, seconds: float = 1.5) -> float:
    try:
        return servicelib.probe_capacity(target.url, target.bodies[0], target.content_type, cpus=cpus,
                                         connections=connections, seconds=seconds, path=target.path,
                                         headers=target.headers)
    except RuntimeError as exc:
        fail(str(exc))


@contextlib.contextmanager
def triton_model(prefix: str, config: str, files: dict[str, bytes] | None = None):
    """Модель на сервере Triton под блокировкой; ошибки сервера — понятным текстом и выходом."""
    try:
        with tritonlib.server_lock():
            name = tritonlib.unique_name(prefix)
            with tritonlib.deploy(name, config, files if files is not None else tritonlib.python_model_files()) as url:
                yield url, name
    except (tritonlib.TritonUnavailable, tritonlib.TritonLoadError, tritonlib.TritonBusy) as exc:
        fail(str(exc))


class Meter:
    """Счётчики модели на сервере до и после замера."""

    def __init__(self, name: str):
        self.name = name
        self.before = tritonlib.parse_metrics(tritonlib.read_metrics(), name)

    def delta(self) -> dict[str, float]:
        return tritonlib.metrics_delta(self.before, tritonlib.parse_metrics(tritonlib.read_metrics(), self.name))
