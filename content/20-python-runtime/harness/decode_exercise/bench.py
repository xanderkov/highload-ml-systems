"""Задание 3: декодирование тела запроса в тензор.

Контракт юнита: encode(img) -> bytes (клиент), decode(body) -> torch.Tensor
(сервер). img — uint8 формы (224, 224, 3); decode должен вернуть float32
формы (3, 224, 224) со значениями img / 255, допуск 1e-6 на элемент.

Замер — decode(encode(img)) для IMAGES изображений, юниты вперемешку.
Корректность проверяется отдельно от замера по каждому изображению:
dtype, форма и значения (по позициям, так что переставленные оси или
каналы не пройдут, даже если сумма та же). Если всё совпало, check юнита —
сумма ожидаемых тензоров, посчитанная харнессом; если нет — NaN, а
сравнение с NaN всегда ложно, и runner ставит correct: false.
"""

import os

# torch и numpy — один поток: задание про копии и разбор, а не про потоки.
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import json
import math
import sys
import time

import numpy as np
import torch

import unit_a
import unit_b

IMAGES = 32
SHAPE = (224, 224, 3)
ATOL = 1e-6


def check(name: str, unit, images: list[np.ndarray], expected: list[torch.Tensor]) -> float:
    for i, (img, want) in enumerate(zip(images, expected)):
        body = unit.encode(img)
        if not isinstance(body, bytes):
            print(f"unit {name}: encode вернул {type(body).__name__}, а нужны bytes", file=sys.stderr)
            return math.nan
        got = unit.decode(body)
        problem = None
        if not isinstance(got, torch.Tensor):
            problem = f"decode вернул {type(got).__name__}, а нужен torch.Tensor"
        elif got.dtype != torch.float32:
            problem = f"dtype {got.dtype}, а нужен torch.float32"
        elif tuple(got.shape) != tuple(want.shape):
            problem = f"форма {tuple(got.shape)}, а нужна {tuple(want.shape)}"
        elif not torch.allclose(got, want, rtol=0, atol=ATOL):
            diff = (got - want).abs().max().item()
            problem = f"значения расходятся с img / 255 (максимум |разницы| {diff:.3g})"
        if problem:
            print(f"unit {name}: изображение {i}: {problem}", file=sys.stderr)
            return math.nan
    return float(sum(want.double().sum().item() for want in expected))


def timed(unit, images: list[np.ndarray]) -> float:
    t0 = time.perf_counter()
    for img in images:
        unit.decode(unit.encode(img))
    return (time.perf_counter() - t0) * 1000


def main() -> None:
    torch.set_num_threads(1)
    rng = np.random.default_rng(0)
    images = [rng.integers(0, 256, SHAPE, dtype=np.uint8) for _ in range(IMAGES)]
    expected = [torch.from_numpy(img).permute(2, 0, 1).to(torch.float32) / 255 for img in images]

    units = {"a": unit_a, "b": unit_b}
    checks = {name: check(name, unit, images, expected) for name, unit in units.items()}

    warmup = int(os.environ["BENCH_WARMUP"])
    repeats = int(os.environ["BENCH_REPEATS"])
    samples = []
    for i in range(warmup + repeats):
        sample = {name: timed(unit, images) for name, unit in units.items()}
        if i >= warmup:
            samples.append(sample)
    for name in units:
        times = sorted(s[name] for s in samples)
        print(f"unit {name}: {IMAGES} изображений, медиана {times[len(times) // 2]:.1f} мс", file=sys.stderr)
    print(json.dumps({"samples": samples, "check": checks}))


main()
