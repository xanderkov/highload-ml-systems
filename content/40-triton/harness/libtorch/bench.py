"""Глава 4: python backend против libtorch при одинаковом батчинге.

Конфиг libtorch — из блока (правка студента или исходный); python backend —
эталон задания главы 2 (stand.PYTHON_CONFIG, dynamic_batching, 1 экземпляр,
3 потока). Харнесс экспортирует widemodel в TorchScript (torch.jit.trace),
грузит обе модели по очереди и подаёт открытую нагрузку STEPS.
"""
import json
import sys
import tempfile
from pathlib import Path

import torch

import servicelib
import stand
import widemodel

STEPS = [300, 700, 1100, 1500]
STEP_S = 2.0
WARMUP_RPS, WARMUP_S = 50, 1.0


def export_traced() -> bytes:
    model = widemodel.make_model()
    with tempfile.TemporaryDirectory() as tmp, torch.inference_mode():
        path = Path(tmp) / "model.pt"
        torch.jit.trace(model, torch.zeros(1, 3, 64, 64)).save(str(path))
        return path.read_bytes()


def run(label, config, files, inputs, load_cpus, lines):
    with stand.triton_model("libtorch", config, files) as (url, name):
        target = stand.triton_target(url, name, inputs)
        warm = stand.load(target, WARMUP_RPS, WARMUP_S, load_cpus)
        if warm.errors or target.wrong(warm.responses, inputs):
            stand.fail(f"{label}: прогрев — {warm.errors} ошибок, неверных ответов "
                       f"{target.wrong(warm.responses, inputs)}")
        for rps in STEPS:
            meter = stand.Meter(name)
            result = stand.load(target, rps, STEP_S, load_cpus, timeout_s=5)
            batch = stand.tritonlib.mean_batch(meter.delta())
            print(f"{label} {rps} RPS: p50 {result.p50():.1f} мс, p99 {result.p99():.1f} мс, "
                  f"ответов/с {result.throughput():.0f}, ошибок {result.errors}, средний батч {batch:.1f}",
                  file=sys.stderr)
            lines.setdefault(f"{label}: p50, мс", []).append({"x": rps, "y": round(result.p50(), 2)})
            lines.setdefault(f"{label}: p99, мс", []).append({"x": rps, "y": round(result.p99(), 2)})


def main() -> None:
    load_cpus, _ = servicelib.split_cpus()
    # Свой torch харнессу нужен только на трассировку и эталонные ответы.
    torch.set_num_threads(1)
    # Экспорт — до любой нагрузки: потоки клиентов замера оставляют за собой
    # арены malloc, и после них трассировке не хватало адресного пространства
    # в лимите задания (RLIMIT_AS) — «can't start new thread».
    model_pt = export_traced()
    inputs = stand.Inputs.make()
    lines = {}
    run("python backend", stand.PYTHON_CONFIG, None, inputs, load_cpus, lines)
    run("libtorch", stand.block_config(), {"1/model.pt": model_pt}, inputs, load_cpus, lines)
    print(json.dumps({"lines": [{"name": n, "points": p} for n, p in lines.items()]}, ensure_ascii=False))


if __name__ == "__main__":
    with stand.exclusive():
        main()
