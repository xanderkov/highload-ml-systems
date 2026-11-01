#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
extern double fn_a(const double *, int);
extern double fn_b(const double *, int);
static double now_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}
int main(void) {
    const int sizes[] = BENCH_SIZES;
    const int n = sizes[0];
    double *a = malloc((size_t)n * sizeof(*a));
    if (!a) return 1;
    /* Binary fractions and all partial sums are exactly representable. */
    long long quarters = 0;
    for (int i = 0; i < n; i++) {
        int q = i % 16 + 1;
        a[i] = q * 0.25;
        quarters += q;
    }
    double (*functions[])(const double *, int) = {fn_a, fn_b};
    const int passes = 4096;
    const double expected = quarters * 0.25 * passes;
    double checks[2] = {0};
    printf("{\"samples\":[");
    for (int r = -BENCH_WARMUP; r < BENCH_REPEATS; r++) {
        double times[2];
        for (int offset = 0; offset < 2; offset++) {
            int k = (r + BENCH_WARMUP + offset) % 2;
            double total = 0;
            double start = now_ms();
            for (int pass = 0; pass < passes; pass++)
                total += functions[k](a, n);
            times[k] = now_ms() - start;
            checks[k] = total;
            if (!isfinite(total) || total != expected) {
                fprintf(stderr, "Результат не совпадает с ожидаемым.\n");
                free(a);
                return 2;
            }
        }
        if (r >= 0) printf("%s{\"a\":%.6f,\"b\":%.6f}", r ? "," : "", times[0], times[1]);
    }
    printf("],\"check\":{\"a\":%.17g,\"b\":%.17g}}\n", checks[0], checks[1]);
    free(a);
    return 0;
}
