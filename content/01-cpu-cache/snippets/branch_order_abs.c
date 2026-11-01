#include <stdlib.h>

// Тот же массив: числа от -100 до 100.
// Например, -7, 12, 0, -3, 5, ...
int sum_filtered(const int *a, int n) {
    int total = 0;
    int magnitudes = 0;
    for (int i = 0; i < n; i++) {
        total += a[i];
        magnitudes += abs(a[i]);
    }
    // x + |x|: 0 для отрицательных,
    // 2*x для положительных.
    return (total + magnitudes) / 2;
}
