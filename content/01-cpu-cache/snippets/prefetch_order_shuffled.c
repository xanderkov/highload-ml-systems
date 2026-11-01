// order содержит те же индексы, но перемешанные.
// Например: 96, 0, 160, 64, 128, 32, ...
// Каждый выбранный элемент читаем ровно один раз.
int sum_order(const int *data, const int *order, int count) {
    int sum = 0;
    for (int i = 0; i < count; i++) {
        sum += data[order[i]];
    }
    return sum;
}
