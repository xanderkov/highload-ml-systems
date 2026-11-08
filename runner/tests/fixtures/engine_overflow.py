def engine(model, inbox, max_batch):
    """Шлёт токены, не глядя на done."""
    inbox.wait()
    for request in inbox.poll(1):
        while True:
            request.send(0)
