import json

import unit_a

# Фикстура: число точек берётся из кода студента (N), форма вывода фиксирована.
n = unit_a.N
print(json.dumps({"lines": [
    {"name": "first", "points": [{"x": float(i), "y": float(i)} for i in range(1, n + 1)]},
    {"name": "second", "points": [{"x": float(i), "y": float(2 * i)} for i in range(1, n + 1)]},
]}))
