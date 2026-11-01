// order содержит индексы элементов data:
// 0, 32, 64, 96, 128, 160, ...
// Читаем элементы по порядку с шагом 128 байт.
int sum_order(const int *data, const int *order, int count) {
    int sum = 0;
    for (int i = 0; i < count; i++) {
        sum += data[order[i]];
    }
    return sum;
}
