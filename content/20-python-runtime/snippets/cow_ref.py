import hashlib

import numpy as np


def key_hash(key: str) -> int:
    """Стабильный 64-битный хэш строки.

    Встроенный hash() не годится: для строк он солится заново в каждом
    запуске интерпретатора. blake2b одинаков везде и всегда.
    """
    digest = hashlib.blake2b(key.encode(), digest_size=8).digest()
    return int.from_bytes(digest, "little", signed=True)


def build_data(records):
    """Те же записи (id, score), но в трёх numpy-массивах вместо миллиона объектов.

    Ключи не хранятся вовсе: только их хэши, отсортированные для двоичного
    поиска. Записи обходим трижды, по разу на массив: каждый кортеж живёт
    одну итерацию, и миллион объектов разом в памяти не оказывается.
    """
    n = len(records)
    hashes = np.fromiter((key_hash(key) for key, _, _ in records), dtype=np.int64, count=n)
    ids = np.fromiter((token_id for _, token_id, _ in records), dtype=np.int64, count=n)
    scores = np.fromiter((score for _, _, score in records), dtype=np.float64, count=n)
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
