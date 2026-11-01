int sum_order(const int *data, const int *order, int count) {
    int sum = 0;
    for (int i = 0; i < count; i++) {
        sum += data[order[i]];
    }
    return sum;
}
