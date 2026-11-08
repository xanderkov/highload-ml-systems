"""Глава 5: занимает ли место клиент, который не дождался ответа.

Модель — конфиг блока (по умолчанию без dynamic_batching: ёмкость около
400 ответов/с). Общая нагрузка TOTAL_RPS выше ёмкости; доля CANCEL_SHARES
запросов — от клиентов, которые закрывают соединение через GIVE_UP_S после
отправки. Если сервер не исполняет брошенные запросы, остальным достаётся
нагрузка ниже ёмкости, и их p99 остаётся маленьким; если исполняет — очередь
растёт так же, как без брошенных. Брошенные запросы шлёт отдельный поток на
своём CPU (не CPU генератора и не CPU сервера). Число исполненных моделью
элементов — из метрик Triton.
"""
import asyncio
import json
import os
import sys
import threading
import time

import servicelib
import stand
import tritonlib

TOTAL_RPS = 500
CANCEL_SHARES = [0, 25, 50]
STEP_S = 3.0
GIVE_UP_S = 0.005


async def _abandon(host: str, port: int, request: bytes, rps: float, duration_s: float) -> None:
    async def one(due: float) -> None:
        await asyncio.sleep(max(0.0, due - time.perf_counter()))
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.write(request)
            await writer.drain()
            await asyncio.sleep(GIVE_UP_S)
            writer.close()
        except OSError:
            pass

    t0 = time.perf_counter() + 0.05
    await asyncio.gather(*(one(t0 + i / rps) for i in range(int(rps * duration_s))))


def abandoning_clients(target, rps: float, duration_s: float, cpu: int) -> threading.Thread:
    host, port = target.url.split("://", 1)[1].rsplit(":", 1)
    body = target.bodies[0]
    head = "".join(f"{k}: {v}\r\n" for k, v in target.headers.items())
    request = (f"POST {target.path} HTTP/1.1\r\nHost: {host}:{port}\r\n{head}Content-Type: {target.content_type}\r\n"
               f"Content-Length: {len(body)}\r\n\r\n").encode() + body

    def run() -> None:
        os.sched_setaffinity(0, {cpu})  # 0 — вызывающий поток
        asyncio.run(_abandon(host, int(port), request, rps, duration_s))

    return threading.Thread(target=run)


def main() -> None:
    load_cpus, available = servicelib.split_cpus()
    spare = sorted(available - servicelib.service_cpus(available))
    if not spare:
        stand.fail("для брошенных клиентов нужен ещё один CPU помимо генератора и сервера")
    inputs = stand.Inputs.make()
    lines = {}
    with stand.triton_model("cancel", stand.block_config()) as (url, name):
        target = stand.triton_target(url, name, inputs)
        stand.load(target, 50, 0.5, load_cpus)  # прогрев
        for share in CANCEL_SHARES:
            staying = TOTAL_RPS * (100 - share) / 100
            meter = stand.Meter(name)
            thread = abandoning_clients(target, TOTAL_RPS * share / 100, STEP_S, spare[0]) if share else None
            if thread:
                thread.start()
            result = stand.load(target, staying, STEP_S, load_cpus, timeout_s=10)
            if thread:
                thread.join()
            time.sleep(1.0)  # дать серверу доработать очередь, прежде чем читать счётчики
            executed = meter.delta()["inference_count"]
            sent = int(TOTAL_RPS * STEP_S)
            print(f"брошено {share} %: p99 дождавшихся {result.p99():.1f} мс, ошибок {result.errors}, "
                  f"модель исполнила {executed:.0f} из {sent} отправленных запросов", file=sys.stderr)
            lines.setdefault("p99 дождавшихся, мс", []).append({"x": share, "y": round(result.p99(), 2)})
            lines.setdefault("исполнено моделью, % от отправленных", []).append(
                {"x": share, "y": round(100 * executed / sent, 2)})
    print(json.dumps({"lines": [{"name": n, "points": p} for n, p in lines.items()]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
