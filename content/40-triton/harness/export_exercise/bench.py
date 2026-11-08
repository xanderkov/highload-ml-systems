"""Задание «экспорт в libtorch»: модель студента в Triton против python backend.

Юнит b (код студента) задаёт export(model, path) и CONFIG. Харнесс:

1. вызывает export(widemodel, path); исключение — трассировка студенту;
   файл не создан — решение неверное (так выглядит стартовый код);
2. грузит model.pt в Triton с CONFIG и сверяет конфиг, как его понял сервер
   (батч разрешён, INPUT__0 / OUTPUT__0 нужных форм);
3. шлёт по одному запросу с батчами BATCHES и сверяет выход с eager widemodel:
   батч 1 проходит, а больший нет — модель «зашита» на батч 1;
4. REPEATS прогонов открытой нагрузки RPS: p99 и goodput при SLO_MS.

Юнит a — точка сравнения: python backend с dynamic batching (stand.PYTHON_CONFIG),
его код не берётся из unit_a. Протокол kind: ab: samples — p99 (мс), check —
1.0 для верного решения, metrics — goodput и goodput_ratio (b к python backend).
"""
import importlib
import json
import math
import os
import statistics
import sys
import tempfile
import traceback
from pathlib import Path

import numpy as np
import torch

import servicelib
import stand
import tritonlib
import widemodel

RPS = 1100
DURATION_S = 2.0
SLO_MS = 50
REPEATS = int(os.environ.get("BENCH_REPEATS", "3"))
BATCHES = [1, 7, 32]
MAX_MODEL_MB = 256


def exported_model() -> bytes | None:
    """Байты model.pt из export студента; None — файл не создан."""
    student = importlib.import_module("unit_b")
    with tempfile.TemporaryDirectory(dir=".") as tmp:
        path = Path(tmp) / "model.pt"
        try:
            student.export(widemodel.make_model(), str(path))
        except Exception:  # noqa: BLE001
            stand.fail("export бросил исключение:\n" + traceback.format_exc())
        if not path.exists():
            print("ваш код: export не сохранил модель по переданному пути", file=sys.stderr)
            return None
        size_mb = path.stat().st_size / 2**20
        if size_mb > MAX_MODEL_MB:
            stand.fail(f"ваш код: model.pt весит {size_mb:.0f} МиБ — больше {MAX_MODEL_MB} МиБ")
        return path.read_bytes()


def check_batches(name: str) -> None:
    torch.manual_seed(7)
    model = widemodel.make_model()
    for size in BATCHES:
        x = torch.randn(size, 3, 64, 64)
        with torch.inference_mode():
            want = model(x).numpy()
        try:
            got = tritonlib.infer(name, x.numpy())
        except tritonlib.TritonInferError as exc:
            hint = (" Батч 1 модель обработала: похоже, при экспорте размер батча оказался зашит в модель"
                    if size > 1 else "")
            stand.fail(f"ваш код: запрос с батчем {size} вернул ошибку: {exc}.{hint}")
        if got.shape != want.shape or not np.allclose(got, want, rtol=1e-4, atol=1e-4):
            stand.fail(f"ваш код: на батче {size} выход модели не совпадает с widemodel "
                       f"(форма {tuple(got.shape)}, ожидалась {tuple(want.shape)})")


def measure(label, config, files, inputs, load_cpus, p99, goodput):
    with stand.triton_model(f"export-{label}", config, files) as (url, name):
        problem = tritonlib.io_problem(tritonlib.model_config(name))
        if problem:
            stand.fail(f"{label}: {problem}")
        if label == "b":
            check_batches(name)
        target = stand.triton_target(url, name, inputs)
        wrong = target.wrong(stand.load(target, 100, 0.5, load_cpus).responses, inputs)
        for _ in range(REPEATS):
            result = stand.load(target, RPS, DURATION_S, load_cpus, timeout_s=5)
            wrong += target.wrong(result.responses, inputs)
            p99.append(result.p99() if result.latencies_ms else DURATION_S * 1000)
            goodput.append(result.goodput(SLO_MS))
            who = "ваш libtorch" if label == "b" else "python backend"
            print(f"{who}: {RPS} RPS — p50 {result.p50():.1f} мс, p99 {result.p99():.1f} мс, "
                  f"goodput {result.goodput(SLO_MS):.0f}/с при SLO {SLO_MS} мс, ошибок {result.errors}",
                  file=sys.stderr)
        return wrong


def main() -> None:
    load_cpus, _ = servicelib.split_cpus()
    inputs = stand.Inputs.make()
    p99 = {"a": [], "b": []}
    goodput = {"a": [], "b": []}
    check = {"a": 1.0}

    model_pt = exported_model()
    if model_pt is None:
        check["b"] = math.nan
        p99["b"] = [DURATION_S * 1000] * REPEATS
        goodput["b"] = [0.0] * REPEATS
    else:
        config = importlib.import_module("unit_b").CONFIG
        wrong = measure("b", config, {"1/model.pt": model_pt}, inputs, load_cpus, p99["b"], goodput["b"])
        if wrong:
            print(f"ваш код: {wrong} ответов не совпали с выходом модели для своего входа", file=sys.stderr)
        check["b"] = math.nan if wrong else 1.0
    measure("a", stand.PYTHON_CONFIG, None, inputs, load_cpus, p99["a"], goodput["a"])

    base = max(statistics.median(goodput["a"]), 1 / DURATION_S)
    metrics = {
        unit: {
            "goodput": round(statistics.median(goodput[unit]), 1),
            "goodput_ratio": round(statistics.median(goodput[unit]) / base, 3),
        }
        for unit in ("a", "b")
    }
    samples = [{"a": a, "b": b} for a, b in zip(p99["a"], p99["b"])]
    print(json.dumps({"samples": samples, "check": check, "metrics": metrics}))


if __name__ == "__main__":
    with stand.exclusive():
        main()
