import numpy as np

# data = [-7, 12, 0, -3, 5, ...], тип int64.
# Сумма положительных значений в примере: 17.
def compute(data):
    return data[data > 0].sum()
