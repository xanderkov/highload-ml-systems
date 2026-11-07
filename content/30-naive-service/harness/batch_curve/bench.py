"""Потолок батча из одного: время модели на элемент при батче 1 … 64.

Код замера — в unit_a.py (snippets/batch_curve.py). Харнесс задаёт один
поток torch, как у воркера сервиса, и меряет две модели с одинаковым входом:
свёрточную tinymodel из подглав 0–1 и widemodel с тяжёлыми весами.
"""
import json
import sys

import torch

import tinymodel
import unit_a
import widemodel


def main() -> None:
    torch.set_num_threads(1)
    lines = []
    for name, model in (("tinymodel (свёртки)", tinymodel.make_model()),
                        ("widemodel (112 МиБ весов)", widemodel.make_model())):
        points = []
        for batch in unit_a.BATCHES:
            ms = unit_a.per_item_ms(model, batch)
            points.append({"x": batch, "y": round(ms, 3)})
            print(f"{name}, батч {batch}: {ms:.3f} мс на элемент, {ms * batch:.2f} мс на вызов", file=sys.stderr)
        best = min(p["y"] for p in points)
        print(f"{name}: самый дешёвый элемент в {points[0]['y'] / best:.1f} раза дешевле, чем при батче 1",
              file=sys.stderr)
        lines.append({"name": f"{name}, мс на элемент", "points": points})
    print(json.dumps({"lines": lines}, ensure_ascii=False))


if __name__ == "__main__":
    main()
