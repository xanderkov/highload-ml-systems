#include <stdio.h>
#include <stdlib.h>
#include <time.h>
extern void fn_a(const int *, const int *, int *, int);
extern void fn_b(const int *, const int *, int *, int);
static double now_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}
int main(void) {
    const int sizes[] = BENCH_SIZES;
    const int n = sizes[0];
    int *a = malloc(n * sizeof(int)), *b = malloc(n * sizeof(int));
    int *out = malloc(n * sizeof(int));
    if (!a || !b || !out) return 1;
    for (int i = 0; i < n; i++) { a[i] = i % 101; b[i] = i % 97; }
    void (*fns[])(const int *, const int *, int *, int) = {fn_a, fn_b};
    printf("{\"samples\":[");
    for (int r = -BENCH_WARMUP; r < BENCH_REPEATS; r++) {
        double times[2];
        for (int offset = 0; offset < 2; offset++) {
            int k = (r + BENCH_WARMUP + offset) % 2;
            for (int i = 0; i < n; i++) out[i] = -1;
            double start = now_ms();
            for (int pass = 0; pass < 512; pass++) fns[k](a, b, out, n);
            times[k] = now_ms() - start;
            for (int i = 0; i < n; i++) if (out[i] != a[i] + b[i]) {
                fprintf(stderr, "Результат не совпадает с ожидаемым.\n"); return 2;
            }
        }
        if (r >= 0) printf("%s{\"a\":%.6f,\"b\":%.6f}", r ? "," : "", times[0], times[1]);
    }
    printf("],\"check\":{\"a\":1,\"b\":1}}\n");
    free(a); free(b); free(out);
    return 0;
}
