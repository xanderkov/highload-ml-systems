// Один и тот же массив в обоих вариантах.
// Числа от -100 до 100 вперемешку, без нулей:
// например, -7, 12, -3, 5, ...
int sum_filtered(const int *a, int n) {
    int sum = 0;
    for (int i = 0; i < n; i++) {
        int x = a[i];
        if (x > 0) {
            sum += 1000 / x;
        }
    }
    return sum;
}
