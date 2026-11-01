/* Складываем все элементы матрицы n×n.
   Матрица лежит в памяти построчно: элемент (i, j) — по индексу i * n + j. */
int matrix_sum(const int *a, int n) {
    int total = 0;
    for (int j = 0; j < n; j++)
        for (int i = 0; i < n; i++)
            total += a[i * n + j];
    return total;
}
