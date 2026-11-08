"""Глава 5: новая версия модели рядом со старой, без остановки сервера.

Версия 1 — python backend с dynamic batching (stand.PYTHON_CONFIG) под
открытой нагрузкой RPS на DURATION_S; запросы идут явно в версию 1. Через
RELOAD_AT_S после начала харнесс в отдельном потоке кладёт версию 2 и
перезагружает модель с version_policy: { all { } } — обе версии рядом. Линии:
p99 и ошибки по окнам WINDOW_S от начала замера; момент перезагрузки и её
длительность — в выводе.
"""
import json
import sys
import threading
import time

import numpy as np

import servicelib
import stand
import tritonlib

RPS = 300
DURATION_S = 6.0
RELOAD_AT_S = 1.5
WINDOW_S = 0.25
SLOW_MS = 100


def main() -> None:
    load_cpus, _ = servicelib.split_cpus()
    inputs = stand.Inputs.make()
    files = tritonlib.python_model_files()
    v2 = {path.replace("1/", "2/", 1): data for path, data in files.items()}
    reload_info = {}
    with stand.triton_model("versions", stand.PYTHON_CONFIG) as (url, name):
        target = stand.triton_target(url, name, inputs)
        target.path = f"/v2/models/{name}/versions/1/infer"
        stand.load(target, 100, 0.5, load_cpus)  # прогрев

        def add_version() -> None:
            time.sleep(RELOAD_AT_S)
            try:
                reload_info["took_s"] = tritonlib.reload(name, stand.PYTHON_CONFIG + "\nversion_policy: { all { } }\n", v2)
            except (tritonlib.TritonLoadError, tritonlib.TritonUnavailable) as exc:
                reload_info["error"] = str(exc)

        thread = threading.Thread(target=add_version)
        thread.start()
        result = stand.load(target, RPS, DURATION_S, load_cpus, timeout_s=10)
        thread.join()
        if "error" in reload_info:
            stand.fail(f"версия 2 не загрузилась: {reload_info['error']}")
        ready = tritonlib.infer(name, inputs.arrays[0])  # последняя версия — уже 2
        if not np.allclose(ready.reshape(-1), inputs.expected[0], rtol=1e-4, atol=1e-4):
            stand.fail("версия 2 отвечает не так, как модель")
        if target.wrong(result.responses, inputs):
            stand.fail("ответы версии 1 не совпадают с выходом модели для своих входов")

    # Латентность i-го запроса: успешные ответы идут в latencies_ms по порядку индексов.
    latency = iter(result.latencies_ms)
    per_request = [next(latency) if raw is not None else None for raw in result.responses]
    windows = int(DURATION_S / WINDOW_S)
    p99_line, errors_line = [], []
    for w in range(windows):
        lo, hi = int(w * WINDOW_S * RPS), int((w + 1) * WINDOW_S * RPS)
        chunk = per_request[lo:hi]
        ok = [v for v in chunk if v is not None]
        x = round((w + 0.5) * WINDOW_S, 3)
        p99_line.append({"x": x, "y": round(float(np.percentile(ok, 99)), 2) if ok else 0.0})
        errors_line.append({"x": x, "y": sum(1 for v in chunk if v is None)})
    print(f"перезагрузка с версией 2: с {RELOAD_AT_S} с, заняла {reload_info['took_s']:.1f} с; "
          f"всего ошибок {result.errors} из {len(result.responses)}; p99 за весь замер {result.p99():.1f} мс; "
          f"дольше {SLOW_MS} мс ждали {sum(1 for v in result.latencies_ms if v > SLOW_MS)} запросов",
          file=sys.stderr)
    for w in range(windows):
        print(f"  {p99_line[w]['x']:.2f} с: p99 {p99_line[w]['y']:.1f} мс, ошибок {errors_line[w]['y']}", file=sys.stderr)
    print(json.dumps({"lines": [{"name": "p99 версии 1, мс", "points": p99_line},
                                {"name": "ошибок в окне", "points": errors_line}]}, ensure_ascii=False))


if __name__ == "__main__":
    with stand.exclusive():
        main()
