// Тот же массив: 0.25, 0.5, 0.75, 1.0, ...
// Четыре независимые цепочки сложений.
double sum_values(const double *a, int n) {
    double s0 = 0, s1 = 0, s2 = 0, s3 = 0;
    int i = 0;
    for (; i + 3 < n; i += 4) {
        s0 += a[i];
        s1 += a[i + 1];
        s2 += a[i + 2];
        s3 += a[i + 3];
    }
    double sum = (s0 + s1) + (s2 + s3);
    for (; i < n; i++) sum += a[i];
    return sum;
}
