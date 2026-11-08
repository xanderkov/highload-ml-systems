"""Глава 0: время шага декода от размера батча.

Код замера — в unit_a.py (snippets/step_curve.py). Харнесс сажает процесс на
три CPU сервиса, задаёт три потока torch и рисует две линии: время шага и
время шага, делённое на батч, — цену одного токена.
"""
import json
import os
import sys

import torch

import stand
import tinygpt
import unit_a


def main() -> None:
    _, service = stand.cpus()
    os.sched_setaffinity(0, service)
    torch.set_num_threads(len(service))
    model = tinygpt.make_model()
    step, per_token = [], []
    for batch in unit_a.BATCHES:
        ms = unit_a.step_ms(model, batch)
        step.append({"x": batch, "y": round(ms, 2)})
        per_token.append({"x": batch, "y": round(ms / batch, 3)})
        print(f"батч {batch}: шаг {ms:.2f} мс, {ms / batch:.3f} мс на токен, "
              f"{1000 * batch / ms:.0f} токенов в секунду", file=sys.stderr)
    print(json.dumps({"lines": [{"name": "шаг, мс", "points": step},
                                {"name": "мс на токен (шаг / батч)", "points": per_token}]}, ensure_ascii=False))


if __name__ == "__main__":
    with stand.exclusive():
        main()
