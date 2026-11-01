import time

N_KEYS = 1_000_000


def build_data() -> dict[str, tuple[int, float]]:
    """«Токенайзер»: словарь токен -> (id, score), как в SentencePiece."""
    return {f"tok{i}": (i, -(i % 5000) / 100.0) for i in range(N_KEYS)}


def worker(data: dict[str, tuple[int, float]], rounds: int) -> int:
    """Только читает: за `rounds` раундов просматривает все записи.

    Ключи собираются заново внутри воркера, поэтому счётчики ссылок
    меняются лишь у хранимых в словаре записей.
    """
    n = len(data)
    total = 0
    for r in range(rounds):
        for i in range(n * r // rounds, n * (r + 1) // rounds):
            token_id, score = data[f"tok{i}"]
            total += token_id + int(score)
        time.sleep(0.25)  # пауза между раундами: график успевает нарисоваться
    return total
