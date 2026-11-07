"""Четыре боли в одном сервисе: тот же сервис, по одному исправлению за шаг.

Варианты (юниты job'а, см. блок four-pains в section.md):
- unit_naive_service.py — async def, JSON, модель прямо в обработчике;
- unit_service_thread.py — модель в потоке (боль №3);
- unit_service_binary.py — + бинарное тело (боль №4);
- unit_b.py (правка студента, иначе unit_a.py) — + WORKERS × TORCH_THREADS (боль №2).

Сервису дано не больше servicelib.SERVICE_MAX_CPUS CPU: так картина одна и
та же на машине с 4 ядрами и на большой, а генератор на одном CPU успевает
довести любой вариант до насыщения. Ступени нагрузки — кратные ёмкости
наивного сервиса C0 (замер закрытым циклом), общие для всех вариантов. Линия
варианта обрывается после ступени, на которой он перестал справляться
(p99 выше STOP_P99_MS или ответов заметно меньше, чем запросов), и на
ступенях выше потолка генератора для его тел.
"""
import ast
import json
import sys
from pathlib import Path

import numpy as np
import torch

import servicelib
import tinymodel

HERE = Path(__file__).resolve().parent
STEP_FACTORS = [1, 1.5, 2, 3, 4]  # ступени: доли ёмкости наивного сервиса C0
STEP_S = 1.5
WARMUP_RPS = 20
WARMUP_S = 0.5
STOP_P99_MS = 1000
MIN_DELIVERED = 0.9  # ответов в секунду не меньше этой доли от RPS
# Потолок генератора на одном CPU (проверено): JSON-тела ~100 КиБ — 520 RPS
# (см. hook/bench.py), бинарные 48 КиБ — 1600 RPS.
GENERATOR_MAX_RPS = {"application/json": 520, "application/octet-stream": 1600}
LIMITS = {"WORKERS": (1, 4), "TORCH_THREADS": (1, 8)}


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(1)


def read_config(path: Path) -> dict[str, int]:
    """WORKERS и TORCH_THREADS — целые константы верхнего уровня файла сервиса."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:
        fail(f"в файле сервиса синтаксическая ошибка, строка {exc.lineno}: {exc.msg}")
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in LIMITS:
                try:
                    found[name] = ast.literal_eval(node.value)
                except ValueError:
                    fail(f"{name} должно быть числом, а не выражением")
    for name, (low, high) in LIMITS.items():
        value = found.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            fail(f"{name} должно быть целым числом от {low} до {high}, сейчас: {value!r}")
    return found


def check_answer(raw: bytes | None, expected: torch.Tensor, name: str) -> None:
    try:
        logits = torch.tensor(json.loads(raw)["logits"])
    except (TypeError, ValueError, KeyError) as exc:
        fail(f"{name}: сервис вернул не {{\"logits\": [...]}}: {exc}")
    if logits.shape != expected.shape or not torch.allclose(logits, expected, atol=1e-4):
        fail(f"{name}: ответ сервиса не совпадает с выходом модели для этого изображения")


def main() -> None:
    load_cpus, available = servicelib.split_cpus()
    cpus = servicelib.service_cpus(available)

    student = HERE / ("unit_b.py" if (HERE / "unit_b.py").exists() else "unit_a.py")
    config = read_config(student)
    workers, threads = config["WORKERS"], config["TORCH_THREADS"]

    pixels = [round(v, 4) for v in tinymodel.make_input(1).flatten().tolist()]
    json_body = json.dumps(pixels).encode()
    binary_body = np.asarray(pixels, dtype=np.float32).tobytes()
    torch.set_num_threads(1)
    with torch.inference_mode():
        expected = tinymodel.make_model()(torch.tensor(pixels).reshape(1, 3, 64, 64))[0]

    variants = [
        ("наивный: async def + JSON", HERE / "unit_naive_service.py", json_body, "application/json", 1, 1),
        ("модель в потоке", HERE / "unit_service_thread.py", json_body, "application/json", 1, 1),
        ("+ бинарное тело", HERE / "unit_service_binary.py", binary_body, "application/octet-stream", 1, 1),
        (f"+ воркеры {workers} × потоки {threads}", student, binary_body, "application/octet-stream", workers, threads),
    ]
    print(f"CPU: генератор {sorted(load_cpus)}, сервис {sorted(cpus)}", file=sys.stderr)

    steps: list[int] = []
    lines = []
    for name, app, body, content_type, n_workers, n_threads in variants:
        points = []
        try:
            with servicelib.start_service(str(app), workers=n_workers, torch_threads=n_threads, cpus=cpus) as url:
                warm = servicelib.run_load(url, rps=WARMUP_RPS, duration_s=WARMUP_S, make_body=lambda i: body,
                                           content_type=content_type, cpus=load_cpus)
                answers = [r for r in warm.responses if r is not None]
                if warm.errors or not answers:
                    fail(f"{name}: прогрев — {warm.errors} ошибок из {len(warm.responses)} запросов")
                check_answer(answers[0], expected, name)

                if not steps:
                    try:
                        c0 = servicelib.probe_capacity(url, body, content_type, cpus=load_cpus)
                    except RuntimeError as exc:
                        fail(str(exc))
                    steps = [max(10, round(c0 * f / 10) * 10) for f in STEP_FACTORS]
                    print(f"ёмкость наивного сервиса C0 ≈ {c0:.0f} ответов/с; ступени {steps} RPS", file=sys.stderr)

                for rps in steps:
                    if rps > GENERATOR_MAX_RPS[content_type]:
                        print(f"{name}: {rps} RPS выше потолка генератора для этих тел — не меряем", file=sys.stderr)
                        break
                    try:
                        result = servicelib.run_load(url, rps=rps, duration_s=STEP_S, make_body=lambda i: body,
                                                     content_type=content_type, cpus=load_cpus)
                    except servicelib.LoadGeneratorLagging:
                        # Перегруженный сервис держит соединения открытыми, и генератор
                        # перестаёт успевать: точку не рисуем, вариант дальше не держит.
                        print(f"{name}: {rps} RPS — сервис перегружен, генератор не держит расписание", file=sys.stderr)
                        break
                    print(
                        f"{name}: {rps} RPS — p50 {result.p50():.1f} мс, p99 {result.p99():.1f} мс, "
                        f"ответов/с {result.throughput():.0f}, ошибок {result.errors}",
                        file=sys.stderr,
                    )
                    points.append({"x": rps, "y": round(result.p99(), 2)})
                    if result.p99() > STOP_P99_MS or result.throughput() < MIN_DELIVERED * rps:
                        break
        except servicelib.ServiceStartError as exc:
            fail(f"{name}: {exc}")
        if points:
            lines.append({"name": name, "points": points})

    print(json.dumps({"lines": lines}, ensure_ascii=False))


if __name__ == "__main__":
    main()
