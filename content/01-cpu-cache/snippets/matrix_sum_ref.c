/* Тот же самый обход, но внешний цикл — по строкам. Соседние обращения идут
   по соседним адресам, и каждая подтянутая кэш-линия используется целиком. */
int matrix_sum(const int *a, int n) {
    int total = 0;
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++)
            total += a[i * n + j];
    return total;
}
