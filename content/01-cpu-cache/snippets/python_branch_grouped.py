# Те же числа: сначала все -1, затем все 1.
# Пример: data = [-1, -1, -1, 1, 1, 1]
# Сумма положительных чисел в примере: 3.
def sum_positive(data):
    total = 0
    for x in data:
        if x > 0:
            total += x
    return total
