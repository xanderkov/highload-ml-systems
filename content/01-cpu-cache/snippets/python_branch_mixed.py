# 4 194 304 числа: -1 и 1 в случайном порядке.
# Пример: data = [1, -1, 1, 1, -1, -1]
# Сумма положительных чисел в примере: 3.
def sum_positive(data):
    total = 0
    for x in data:
        if x > 0:
            total += x
    return total
