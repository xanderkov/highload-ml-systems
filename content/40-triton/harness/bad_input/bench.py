"""Глава 5: битый вход в батче — кто получает ошибку.

Модель — python backend с dynamic batching (stand.PYTHON_CONFIG). Наш model.py
отвечает ошибкой на вход, у которого первый элемент равен BAD_INPUT, и только
этому запросу (tritonlib.BAD_INPUT, triton_model.py). Нагрузка RPS; каждый
EVERY-й вход битый, EVERY из BAD_EVERY. Линии: доля ошибок среди нормальных и
среди битых входов и средний батч — чтобы было видно, что битые входы
действительно попадали в батчи вместе с нормальными.
"""
import json
import sys

import numpy as np

import servicelib
import stand
import tritonlib

RPS = 700
STEP_S = 2.0
BAD_EVERY = [20, 10, 5]


def main() -> None:
    load_cpus, _ = servicelib.split_cpus()
    inputs = stand.Inputs.make()
    lines = {}
    with stand.triton_model("bad", stand.PYTHON_CONFIG) as (url, name):
        good = stand.triton_target(url, name, inputs)
        stand.load(good, 100, 0.5, load_cpus)  # прогрев
        bad_array = np.zeros((1, 3, 64, 64), dtype=np.float32)
        bad_array.flat[0] = tritonlib.BAD_INPUT
        bad_body, _ = tritonlib.v2_body(bad_array)
        for every in BAD_EVERY:
            target = stand.triton_target(url, name, inputs)
            target.bodies = [bad_body if i % every == every - 1 else good.body(i) for i in range(every * len(good.bodies))]
            meter = stand.Meter(name)
            result = stand.load(target, RPS, STEP_S, load_cpus, timeout_s=5)
            batch = tritonlib.mean_batch(meter.delta())
            is_bad = [i % len(target.bodies) % every == every - 1 for i in range(len(result.responses))]
            bad_errors = sum(1 for r, b in zip(result.responses, is_bad) if b and r is None)
            good_errors = sum(1 for r, b in zip(result.responses, is_bad) if not b and r is None)
            wrong = 0
            for i, (raw, b) in enumerate(zip(result.responses, is_bad)):
                if raw is None or b:
                    continue
                position = i % len(target.bodies)
                got = tritonlib.parse_v2_response(raw).reshape(-1)
                if not np.allclose(got, inputs.expected[position % len(inputs.arrays)], rtol=1e-4, atol=1e-4):
                    wrong += 1
            if wrong:
                stand.fail(f"{wrong} нормальных ответов не совпали с выходом модели для своего входа")
            bad_total = sum(is_bad)
            good_total = len(is_bad) - bad_total
            share = 100 / every
            print(f"битый каждый {every}-й ({share:.0f} %): ошибок среди битых {bad_errors}/{bad_total}, "
                  f"среди нормальных {good_errors}/{good_total}, средний батч {batch:.1f}", file=sys.stderr)
            lines.setdefault("ошибок среди битых, %", []).append({"x": share, "y": round(100 * bad_errors / bad_total, 2)})
            lines.setdefault("ошибок среди нормальных, %", []).append(
                {"x": share, "y": round(100 * good_errors / good_total, 2)})
            lines.setdefault("средний батч, штук", []).append({"x": share, "y": round(batch, 2)})
    print(json.dumps({"lines": [{"name": n, "points": p} for n, p in lines.items()]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
