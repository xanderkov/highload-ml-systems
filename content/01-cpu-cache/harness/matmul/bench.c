#include <stdio.h>
#include <stdlib.h>
#include <time.h>

extern double fn_a(const double *a, const double *b, int n);
extern double fn_b(const double *a, const double *b, int n);

static double now_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

int main(void) {
    const int sizes[] = BENCH_SIZES;
    const int n = sizes[0];
    const size_t total = (size_t)n * (size_t)n;

    double *a = malloc(total * sizeof(double));
    double *b = malloc(total * sizeof(double));
    if (a == NULL || b == NULL) {
        fprintf(stderr, "не хватило памяти на две матрицы %d x %d\n", n, n);
        return 1;
    }
    /* Детерминированное заполнение: оба варианта обязаны получить один и тот
       же ответ. Значения кратны 0.25 — точно представимы в double, так что
       расхождение между вариантами возьмётся только из порядка сложений. */
    for (int i = 0; i < n; i++)
        for (int j = 0; j < n; j++) {
            double v = (double)((i * 31 + j * 17) % 13) * 0.25;
            a[(size_t)i * n + j] = v;
            b[(size_t)i * n + j] = v + 0.5;
        }

    double check_a = 0, check_b = 0;
    for (int w = 0; w < BENCH_WARMUP; w++) { check_a = fn_a(a, b, n); check_b = fn_b(a, b, n); }

    /* Инварианты протокола замера — те же, что в harness/matrix_sum/bench.c:
       warmup отброшен, A и B чередуются внутри повтора, наружу уходит ровно
       одна строка JSON с ровно BENCH_REPEATS замерами. */
    printf("{\"samples\":[");
    for (int r = 0; r < BENCH_REPEATS; r++) {
        double t0 = now_ms(); check_a = fn_a(a, b, n); double t1 = now_ms();
        double t2 = now_ms(); check_b = fn_b(a, b, n); double t3 = now_ms();
        printf("%s{\"a\":%.6f,\"b\":%.6f}", r ? "," : "", t1 - t0, t3 - t2);
    }
    printf("],\"check\":{\"a\":%.17g,\"b\":%.17g}}\n", check_a, check_b);

    free(a);
    free(b);
    return 0;
}
