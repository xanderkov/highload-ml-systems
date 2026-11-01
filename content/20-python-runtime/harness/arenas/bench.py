"""Эксперимент: после `del` Python думает, что память свободна, а ОС её не видит.

Четыре стадии: 0 старт, 1 создано, 2 удалено 90 % вразброс, 3 удалено всё.
На каждой стадии замеряем:

- `tracemalloc`: сколько памяти занимают живые объекты Python;
- `RSS`: сколько страниц процесса резидентны с точки зрения ОС.

tracemalloc хранит запись о каждом блоке и сам раздувает RSS, поэтому
две серии снимаются в разных процессах (fork), а в график идёт
прирост относительно стадии 0.
"""

import json
import sys
import tracemalloc

import forklib
import memlib

import unit_a


def run(traced: bool) -> list[float]:
    """Прогоняет четыре стадии и возвращает прирост в МиБ относительно старта."""
    if traced:
        tracemalloc.start()

    def measure() -> float:
        if traced:
            return tracemalloc.get_traced_memory()[0] / 2**20
        return memlib.rss_mib()

    base = measure()
    values = [0.0]
    objects = unit_a.create()
    values.append(measure() - base)
    objects = unit_a.delete_scattered(objects)
    values.append(measure() - base)
    unit_a.delete_all(objects)
    del objects
    values.append(measure() - base)
    return values


def in_child(traced: bool) -> list[float]:
    """Замер в отдельном процессе: память одного прогона не достаётся другому."""
    name = "tracemalloc run" if traced else "RSS run"
    return json.loads(forklib.run_in_child(lambda: json.dumps(run(traced)).encode(), name))


def main() -> None:
    traced = in_child(True)
    rss = in_child(False)
    print(f"tracemalloc: {traced}\nRSS: {rss}", file=sys.stderr)
    lines = [
        {"name": "tracemalloc", "points": [{"x": i, "y": round(v, 2)} for i, v in enumerate(traced)]},
        {"name": "RSS", "points": [{"x": i, "y": round(v, 2)} for i, v in enumerate(rss)]},
    ]
    print(json.dumps({"lines": lines}))


main()
