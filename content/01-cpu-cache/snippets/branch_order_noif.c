// Тот же массив: числа от -100 до 100, без нулей.
// Например, -7, 12, -3, 5, ...
int sum_filtered(const int *a, int n) {
    int sum = 0;
    for (int i = 0; i < n; i++) {
        int x = a[i];
        // Для отрицательных чисел множитель равен 0.
        sum += (1000 / x) * (x > 0);
    }
    return sum;
}
