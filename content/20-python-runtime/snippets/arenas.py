"""Миллион мелких объектов, из которых потом удаляется 90 %.

Объекты берём мелкие: кортеж `(int, float)` занимает 56 байт, `int` 32 и
`float` 24. Всё это меньше 512 байт, поэтому живёт в арене pymalloc, а не
в malloc. Большие объекты (строка на сотни килобайт) устроены иначе.
"""

N_OBJECTS = 1_000_000
KEEP_EVERY = 10


def create() -> list[tuple[int, float]]:
    """Стадия 1: создаёт N_OBJECTS кортежей подряд, а значит рядом в памяти."""
    return [(i, i / 2) for i in range(N_OBJECTS)]


def delete_scattered(objects: list) -> list:
    """Стадия 2: оставляет каждый KEEP_EVERY-й объект, остальные 90 % удаляет.

    Живые объекты разбросаны по всем пулам и аренам равномерно.
    """
    return objects[::KEEP_EVERY]


def delete_all(objects: list) -> list:
    """Стадия 3: удаляет всё, что осталось."""
    objects.clear()
    return objects
