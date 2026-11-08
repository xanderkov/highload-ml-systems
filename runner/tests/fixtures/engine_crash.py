def engine(model, inbox, max_batch):
    inbox.wait()
    raise ValueError("boom")
