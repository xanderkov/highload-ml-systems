import gc

N_KEYS = 1_000_000


def build_data() -> dict[str, tuple[int, float]]:
    """«Токенайзер»: словарь токен -> (id, score), как в SentencePiece."""
    return {f"tok{i}": (i, -(i % 5000) / 100.0) for i in range(N_KEYS)}


def prepare(data) -> None:
    """Вызывается в родителе перед fork: убираем всё живое из поля зрения GC."""
    gc.freeze()


def lookup(data, key: str) -> tuple[int, float]:
    """Запись (id, score) по ключу. Вызывается в воркере на каждый ключ."""
    return data[key]
