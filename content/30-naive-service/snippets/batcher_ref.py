"""Эталон: первый элемент ждём сколько угодно, остальные — до max_delay."""
import asyncio


async def collect_batch(queue: asyncio.Queue, max_batch_size: int, max_delay: float) -> list:
    batch = [await queue.get()]
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max_delay
    while len(batch) < max_batch_size:
        # Всё, что уже ждёт в очереди, забираем без ожидания.
        try:
            batch.append(queue.get_nowait())
            continue
        except asyncio.QueueEmpty:
            pass
        timeout = deadline - loop.time()
        if timeout <= 0:
            break
        try:
            batch.append(await asyncio.wait_for(queue.get(), timeout))
        except TimeoutError:
            break
    return batch
