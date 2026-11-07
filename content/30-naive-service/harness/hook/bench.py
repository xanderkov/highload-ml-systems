"""Крючок раздела: наивный сервис под растущей открытой нагрузкой.

Сервис из кода блока (unit_a.py) поднимается один раз: один воркер uvicorn,
у torch TORCH_THREADS поток(ов), процессы сервиса привязаны ко всем CPU,
кроме одного — на нём работает генератор нагрузки (servicelib.split_cpus).
После прогрева — замер ёмкости C: PROBE_CONNECTIONS соединений шлют запросы
подряд (закрытый цикл, у сервиса всегда есть очередь), C — ответов в секунду.
Ступени зависят от машины: доли C до насыщения и C + OVERLOAD_RPS выше него.
На каждой ступени открытая нагрузка STEP_S секунд — запросы уходят по
расписанию, не дожидаясь ответов на предыдущие.

Перегрузка задаётся абсолютным превышением, а не долей C: генератор на одном
CPU с этими телами (~100 КиБ JSON) отстаёт от расписания тем раньше, чем
больше превышение и выше сам RPS. Замеры: при C ≈ 220 превышение +100 ещё
честно, +130 — уже lag; при C ≈ 450 +60 честно, +80 — lag; без перегрузки
генератор держит 700 RPS. Поэтому ступени C + 30 и C + 60, а потолок
GENERATOR_MAX_RPS — самая высокая проверенная верхняя ступень (510 RPS при
C ≈ 450) с округлением. Выше харнесс прямо говорит, что машина слишком
быстрая, а не рисует сомнительный замер. Отставание на любой ступени ловит и
сам run_load (LoadGeneratorLagging).
"""
import json
import sys
import time
from pathlib import Path

import torch

import servicelib
import tinymodel

TORCH_THREADS = 1
UNDER_FRACTIONS = [0.25, 0.5, 0.75, 0.9]  # ступени ниже ёмкости, доли C
OVERLOAD_RPS = [30, 60]  # ступени выше ёмкости: C + столько RPS
GENERATOR_MAX_RPS = 520  # проверенная верхняя ступень для этих тел, см. docstring
STEP_S = 3.0
WARMUP_RPS = 20
WARMUP_S = 1.0
PROBE_CONNECTIONS = 4
PROBE_S = 1.5


def main() -> None:
    load_cpus, service_cpus = servicelib.split_cpus()
    app_path = Path(__file__).resolve().parent / "unit_a.py"

    x = tinymodel.make_input(1)
    # Пиксели округлены до 4 знаков: так выглядит обычный JSON с изображением.
    pixels = [round(v, 4) for v in x.flatten().tolist()]
    body = json.dumps(pixels).encode()
    torch.set_num_threads(1)
    with torch.inference_mode():
        expected = tinymodel.make_model()(torch.tensor(pixels).reshape(1, 3, 64, 64))[0]

    def make_body(i: int) -> bytes:
        return body

    print(
        f"CPU: генератор {sorted(load_cpus)}, сервис {len(service_cpus)} шт.; "
        f"тело запроса {len(body) / 1024:.0f} КиБ JSON; потоков torch {TORCH_THREADS}",
        file=sys.stderr,
    )

    p50, p99, cpu = [], [], []
    with servicelib.start_service(str(app_path), workers=1, torch_threads=TORCH_THREADS,
                                  cpus=service_cpus) as url:
        warm = servicelib.run_load(url, rps=WARMUP_RPS, duration_s=WARMUP_S, make_body=make_body,
                                   content_type="application/json", cpus=load_cpus)
        answers = [r for r in warm.responses if r is not None]
        if warm.errors or not answers:
            print(f"прогрев: {warm.errors} ошибок из {len(warm.responses)} запросов", file=sys.stderr)
            sys.exit(1)
        try:
            logits = torch.tensor(json.loads(answers[0])["logits"])
        except (ValueError, KeyError, TypeError) as exc:
            print(f"сервис вернул не {{\"logits\": [...]}}: {exc}", file=sys.stderr)
            sys.exit(1)
        if logits.shape != expected.shape or not torch.allclose(logits, expected, atol=1e-4):
            print("ответ сервиса не совпадает с выходом модели для этого изображения", file=sys.stderr)
            sys.exit(1)

        try:
            capacity = servicelib.probe_capacity(url, body, "application/json", cpus=load_cpus,
                                                 connections=PROBE_CONNECTIONS, seconds=PROBE_S)
        except RuntimeError as exc:
            print(exc, file=sys.stderr)
            sys.exit(1)
        steps = [max(10, round(capacity * f / 10) * 10) for f in UNDER_FRACTIONS]
        steps += [round(capacity / 10) * 10 + extra for extra in OVERLOAD_RPS]
        print(f"ёмкость сервиса C ≈ {capacity:.0f} ответов/с; ступени {steps} RPS", file=sys.stderr)
        if steps[-1] > GENERATOR_MAX_RPS:
            print(
                f"сервис на этой машине слишком быстрый для крючка: нужна нагрузка {steps[-1]} RPS, "
                f"а генератор нагрузки на одном CPU проверен только до {GENERATOR_MAX_RPS} RPS "
                f"с телами по {len(body) / 1024:.0f} КиБ. Замер выше был бы нечестным",
                file=sys.stderr,
            )
            sys.exit(1)

        for rps in steps:
            cpu_before = servicelib.cpu_seconds(url.pids())
            started = time.perf_counter()
            result = servicelib.run_load(url, rps=rps, duration_s=STEP_S, make_body=make_body,
                                         content_type="application/json", cpus=load_cpus)
            wall = time.perf_counter() - started
            busy = servicelib.cpu_seconds(url.pids()) - cpu_before
            share = 100 * busy / (wall * len(service_cpus))
            print(
                f"{rps} RPS: p50 {result.p50():.1f} мс, p99 {result.p99():.1f} мс, "
                f"ответов/с {result.throughput():.0f}, ошибок {result.errors}, lag генератора p99 {result.lag_ms_p99:.2f} мс, "
                f"CPU сервиса {busy / wall:.2f} ядра из {len(service_cpus)} ({share:.1f} %)",
                file=sys.stderr,
            )
            p50.append({"x": rps, "y": round(result.p50(), 2)})
            p99.append({"x": rps, "y": round(result.p99(), 2)})
            cpu.append({"x": rps, "y": round(share, 2)})

    print(json.dumps({"lines": [
        {"name": "p50, мс", "points": p50},
        {"name": "p99, мс", "points": p99},
        {"name": f"CPU сервиса, % от {len(service_cpus)} CPU", "points": cpu},
    ]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
