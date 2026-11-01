import json

# Фикстура: игнорирует код студента и печатает фиксированные метрики.
samples = [{"a": 2.0, "b": 1.0} for _ in range(3)]
print(json.dumps({
    "samples": samples,
    "check": {"a": 1.0, "b": 1.0},
    "metrics": {"a": {"m": 0.9}, "b": {"m": 0.5}},
}))
