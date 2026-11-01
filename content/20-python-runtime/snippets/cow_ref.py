import hashlib

import numpy as np

N_KEYS = 1_000_000


def key_hash(key: str) -> int:
    """Стабильный 64-битный хэш строки.

    Встроенный hash() не годится: для строк он солится заново в каждом
    запуске интерпретатора. blake2b одинаков везде и всегда.
    """
    digest = hashlib.blake2b(key.encode(), digest_size=8).digest()
    return int.from_bytes(digest, "little", signed=True)


def build_data():
    """Те же записи (id, score), но в трёх numpy-массивах вместо миллиона объектов.

    Ключи не хранятся вовсе: только их хэши, отсортированные для двоичного
    поиска. Каждый ключ живёт ровно одну итерацию цикла.
    """
    hashes = np.fromiter((key_hash(f"tok{i}") for i in range(N_KEYS)), dtype=np.int64, count=N_KEYS)
    ids = np.arange(N_KEYS, dtype=np.int64)
    scores = -(ids % 5000) / 100.0
    order = np.argsort(hashes, kind="stable")
    hashes, ids, scores = hashes[order], ids[order], scores[order]
    # Два ключа с одинаковым хэшем сделали бы поиск неоднозначным.
    # Для 1M ключей и 64 бит вероятность ~3e-8, но проверить дёшево.
    if np.any(hashes[1:] == hashes[:-1]):
        raise ValueError("коллизия 64-битных хэшей ключей")
    return hashes, ids, scores


def prepare(data) -> None:
    """Готовить нечего: массивы — это несколько больших буферов без refcount."""


def lookup(data, key: str) -> tuple[int, float]:
    hashes, ids, scores = data
    h = key_hash(key)
    pos = int(np.searchsorted(hashes, h))
    if pos == len(hashes) or hashes[pos] != h:
        raise KeyError(key)
    return int(ids[pos]), float(scores[pos])
