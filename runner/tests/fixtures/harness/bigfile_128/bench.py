import json

# Фикстура: пишет файл в 100 МиБ — больше лимита по умолчанию (64 МиБ).
with open("big.bin", "wb") as handle:
    for _ in range(100):
        handle.write(b"\0" * (1 << 20))
print(json.dumps({"lines": [{"name": "ok", "points": [{"x": 1.0, "y": 1.0}]}]}))
