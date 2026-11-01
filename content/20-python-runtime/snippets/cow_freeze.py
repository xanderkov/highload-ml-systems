import gc


def build_data(records) -> dict[str, tuple[int, float]]:
    """«Токенайзер»: словарь токен -> (id, score), как в SentencePiece.

    records — записи (ключ, id, score) для ключей tok0, tok1, …; обойти их
    можно сколько угодно раз, len(records) — их число.
    """
    return {key: (token_id, score) for key, token_id, score in records}


def prepare(data) -> None:
    """Вызывается в родителе перед fork: убираем всё живое из поля зрения GC."""
    gc.freeze()


def lookup(data, key: str) -> tuple[int, float]:
    """Запись (id, score) по ключу. Вызывается в воркере на каждый ключ."""
    return data[key]
