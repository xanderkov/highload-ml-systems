import numpy as np

# data = [-200, -50, 50, 200, ...]
# После ограничения: [-100, -50, 50, 100, ...]
# Для этих четырёх значений результат: 25000.
def compute(data):
    clipped = np.clip(data, -100, 100)
    return (clipped * clipped).sum()
