#include <stdio.h>
#include <stdlib.h>
#include <time.h>

extern long long fn_a(int *, int);
extern long long fn_b(int *, int);

static double now_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

int main(void) {
    const long long bytes_a = fn_a(NULL, 0), bytes_b = fn_b(NULL, 0);
    if (bytes_a <= 0 || bytes_b <= 0 || bytes_a + bytes_b > 1024LL * 1024 * 1024) {
        fprintf(stderr, "Массивы превышают лимит памяти 1 ГиБ.\n");
        return 1;
    }
    int *a = malloc((size_t)bytes_a), *b = malloc((size_t)bytes_b);
    if (!a || !b) {
        fprintf(stderr, "Не удалось выделить память: лимит процесса — 1 ГиБ.\n");
        free(a); free(b);
        return 1;
    }
    /* Fill and touch all pages before measuring either layout. */
    fn_a(a, 1); fn_b(b, 1);
    long long check_a = 0, check_b = 0;
    for (int i = 0; i < BENCH_WARMUP; i++) {
        check_a = fn_a(a, 2); check_b = fn_b(b, 2);
    }
    printf("{\"samples\":[");
    for (int i = 0; i < BENCH_REPEATS; i++) {
        double ta, tb, t0;
        if (i % 2 == 0) {
            t0 = now_ms(); check_a = fn_a(a, 2); ta = now_ms() - t0;
            t0 = now_ms(); check_b = fn_b(b, 2); tb = now_ms() - t0;
        } else {
            t0 = now_ms(); check_b = fn_b(b, 2); tb = now_ms() - t0;
            t0 = now_ms(); check_a = fn_a(a, 2); ta = now_ms() - t0;
        }
        printf("%s{\"a\":%.6f,\"b\":%.6f}", i ? "," : "", ta, tb);
    }
    printf("],\"check\":{\"a\":%lld,\"b\":%lld}}\n", check_a, check_b);
    free(a); free(b);
    return 0;
}
