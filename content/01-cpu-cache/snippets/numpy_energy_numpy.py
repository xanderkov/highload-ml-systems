import numpy as np

# data = [-2.0, -0.5, 0.5, 2.0, ...]
# После ограничения: [-1.0, -0.5, 0.5, 1.0, ...]
# Для этих четырёх значений результат: 2.5.
def compute(data):
    clipped = np.clip(data, -1.0, 1.0)
    return (clipped * clipped).sum()
