import torch

from tinygpt import KVBatch


def engine(model, inbox, max_batch):
    """Continuous batching: батч собирается из шагов, а не из запросов."""
    batch = KVBatch()
    running = []  # запросы в строках батча, по порядку строк
    last = []     # последний токен каждой строки
    while not inbox.closed or running:
        if not running:
            inbox.wait()  # работы нет — ждём новый запрос, а не крутим цикл впустую
        # Между шагами: принять новые запросы, пока есть место.
        for request in inbox.poll(max_batch - len(running)):
            token, kv = model.prefill(request.prompt)
            batch.add(kv)
            running.append(request)
            last.append(token)
            request.send(token)
        # Убрать закончившиеся — их место займут новые на следующем шаге.
        keep = [row for row, request in enumerate(running) if not request.done]
        if len(keep) < len(running):
            batch.keep(keep)
            running = [running[row] for row in keep]
            last = [last[row] for row in keep]
        if not running:
            continue
        # Один шаг для всех строк сразу.
        last = model.decode_step(batch, torch.tensor(last)).tolist()
        for request, token in zip(running, last):
            request.send(token)
