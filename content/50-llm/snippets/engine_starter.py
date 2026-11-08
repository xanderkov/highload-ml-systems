import torch

from tinygpt import KVBatch


def engine(model, inbox, max_batch):
    """Статический батч: взяли запросы, крутим, пока не закончит самый длинный."""
    while not inbox.closed:
        inbox.wait()  # ждём хотя бы один запрос
        requests = inbox.poll(max_batch)
        if not requests:
            continue
        batch = KVBatch()
        last = []
        for request in requests:
            token, kv = model.prefill(request.prompt)
            batch.add(kv)
            last.append(token)
            request.send(token)
        # Батч живёт, пока не закончит самый длинный ответ. Новые запросы
        # тем временем ждут в inbox, а закончившиеся строки считаются впустую.
        while not all(request.done for request in requests):
            last = model.decode_step(batch, torch.tensor(last)).tolist()
            for request, token in zip(requests, last):
                if not request.done:
                    request.send(token)
