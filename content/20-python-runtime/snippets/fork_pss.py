import time

N_KEYS = 1_000_000
# Значения — большие целые (~130 байт каждое): так объекты значений занимают
# заметную часть памяти словаря, как записи токенайзера со структурой внутри.
PAD = 1 << 800


def build_data() -> dict[str, int]:
    """«Токенайзер»: словарь токен -> запись."""
    return {f"tok{i}": PAD + i for i in range(N_KEYS)}


def worker(data: dict[str, int], rounds: int) -> int:
    """Только читает: за `rounds` раундов просматривает все значения.

    Ключи собираются заново внутри воркера, поэтому счётчики ссылок
    меняются лишь у хранимых в словаре значений.
    """
    step = N_KEYS // rounds
    total = 0
    for r in range(rounds):
        for i in range(r * step, (r + 1) * step):
            total += data[f"tok{i}"] & 0xFFFF
        time.sleep(0.25)  # пауза между раундами: график успевает нарисоваться
    return total
