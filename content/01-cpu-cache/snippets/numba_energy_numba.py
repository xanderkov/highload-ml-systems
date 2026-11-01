from numba import njit

# data = [-200, -50, 50, 200, ...]
# После ограничения: [-100, -50, 50, 100, ...]
# Для этих четырёх значений результат: 25000.
@njit
def compute(data):
    total = 0
    for x in data:
        if x < -100:
            x = -100
        elif x > 100:
            x = 100
        total += x * x
    return total
