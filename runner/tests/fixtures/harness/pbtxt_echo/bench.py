import json
from pathlib import Path

# Фикстура: юниты языка pbtxt лежат текстовыми файлами рядом с bench.py.
text = Path("unit_a.pbtxt").read_text(encoding="utf-8").strip()
print(json.dumps({"lines": [{"name": text, "points": [{"x": 1.0, "y": 1.0}]}]}, ensure_ascii=False))
