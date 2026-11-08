import time


def engine(model, inbox, max_batch):
    """Принимает запросы и никогда не отдаёт токенов."""
    while True:
        inbox.poll(max_batch)
        time.sleep(0.01)
