"""Эксперимент: синхронная модель внутри async def и лаг event loop.

В одном цикле asyncio работают две задачи:

- «пульс» — в цикле засыпает на PULSE_MS и записывает, на сколько позже
  проснулся (лаг цикла). Так ведёт себя любой лёгкий обработчик, например
  /health: он получает управление, только когда цикл свободен;
- «клиент» — каждые INTERVAL_MS запускает задачу-запрос handle(model, x).

Прогон делается дважды: с эталонным блокирующим handle харнесса (линия
blocking) и с handle из кода блока (линия «ваш handle»). x — мс от старта
прогона, y — лаг цикла в мс.
"""

import os

# Число потоков задаётся до импорта torch, через переменную окружения: так
# оно одинаково и в главном потоке, и в рабочих потоках asyncio.to_thread.
# Один поток на вызов: инференс занимает одно ядро и длится одинаково в обоих
# прогонах; эксперимент про лаг цикла, а не про пропускную способность.
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"

import asyncio
import inspect
import json
import statistics
import sys
import time

import torch

import tinymodel

# Код блока приходит юнитом b (редактор), исходный сниппет — юнитом a.
try:
    import unit_b as student
except ImportError:
    import unit_a as student

PULSE_MS = 10
INTERVAL_MS = 100
REQUESTS = 20
BATCH = 16  # ≈ 45 мс инференса на одном потоке


async def blocking_handle(model, x):
    return model(x)


async def run(handle, model, x, expected) -> list[tuple[float, float]]:
    loop = asyncio.get_running_loop()
    start = loop.time()
    done = asyncio.Event()
    samples = []

    async def pulse() -> None:
        while not done.is_set():
            t0 = loop.time()
            await asyncio.sleep(PULSE_MS / 1000)
            lag = loop.time() - t0 - PULSE_MS / 1000
            samples.append(((t0 - start) * 1000, max(lag, 0.0) * 1000))

    async def request() -> None:
        out = await handle(model, x)
        if not isinstance(out, torch.Tensor) or out.shape != expected.shape or not torch.allclose(out, expected):
            raise RuntimeError("handle вернул не выход модели для x")

    pulser = asyncio.create_task(pulse())
    tasks = []
    for i in range(REQUESTS):
        # Запросы приходят по расписанию от старта, а не «через 100 мс после
        # предыдущего»: задержки цикла не сдвигают расписание клиента.
        await asyncio.sleep(max(0.0, start + i * INTERVAL_MS / 1000 - loop.time()))
        tasks.append(asyncio.create_task(request()))
    await asyncio.gather(*tasks)
    done.set()
    await pulser
    return samples


def main() -> None:
    torch.set_num_threads(1)
    model = tinymodel.make_model()
    # Без графа autograd в любом потоке: inference_mode действует только в
    # том потоке, где включён, а requires_grad=False — у самих весов.
    for param in model.parameters():
        param.requires_grad_(False)
    x = tinymodel.make_input(BATCH)
    for _ in range(3):
        expected = model(x)

    if not inspect.iscoroutinefunction(getattr(student, "handle", None)):
        print("в коде блока нужна функция async def handle(model, x)", file=sys.stderr)
        sys.exit(1)

    t0 = time.perf_counter()
    model(x)
    print(f"инференс батча {BATCH}: {(time.perf_counter() - t0) * 1000:.0f} мс", file=sys.stderr)

    lines = []
    for name, handle in (("blocking", blocking_handle), ("ваш handle", student.handle)):
        samples = asyncio.run(run(handle, model, x, expected))
        lags = [lag for _, lag in samples]
        print(
            f"{name}: {len(lags)} пульсов, лаг медиана {statistics.median(lags):.1f} мс, "
            f"максимум {max(lags):.1f} мс",
            file=sys.stderr,
        )
        lines.append({"name": name, "points": [{"x": round(t), "y": round(lag, 2)} for t, lag in samples]})
    print(json.dumps({"lines": lines}, ensure_ascii=False))


main()
