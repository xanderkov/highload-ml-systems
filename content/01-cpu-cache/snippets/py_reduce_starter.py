def reduce_rows(a):
    """Сумма построчных максимумов матрицы a (numpy-массив формы n x n).

    Сейчас это честный цикл на Python: каждое a[i, j] достаёт из массива одно
    число и заворачивает его в объект numpy.float64 — отдельный объект в куче
    на каждое обращение. Данные лежат подряд, а работа с ними идёт вразнобой.

    Перепишите так, чтобы обход выполнял NumPy, а не интерпретатор.
    """
    total = 0.0
    for i in range(a.shape[0]):
        best = a[i, 0]
        for j in range(a.shape[1]):
            if a[i, j] > best:
                best = a[i, j]
        total += float(best)
    return total
