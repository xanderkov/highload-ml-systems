# data = [-2.0, -0.5, 0.5, 2.0, ...]
# После ограничения: [-1.0, -0.5, 0.5, 1.0, ...]
# Для этих четырёх значений результат: 2.5.
def compute(data):
    total = 0.0
    for x in data:
        if x < -1.0:
            x = -1.0
        elif x > 1.0:
            x = 1.0
        total += x * x
    return total
