// 4096 чисел: 0.25, 0.5, 0.75, 1.0, ...
// Четыре сложения, каждое ждёт предыдущую сумму.
double sum_values(const double *a, int n) {
    double sum = 0;
    int i = 0;
    for (; i + 3 < n; i += 4) {
        sum += a[i];
        sum += a[i + 1];
        sum += a[i + 2];
        sum += a[i + 3];
    }
    for (; i < n; i++) sum += a[i];
    return sum;
}
