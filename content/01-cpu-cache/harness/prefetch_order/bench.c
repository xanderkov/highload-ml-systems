#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

extern int fn_a(const int *, const int *, int);
extern int fn_b(const int *, const int *, int);

/* 128-byte spacing avoids reusing the same cache line on both common
   64-byte x86 and 128-byte Apple Silicon data caches. */
enum { STEP = 32 };
static uint32_t rng = 0x12345678;
static uint32_t random_u32(void) {
    rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5;
    return rng;
}
static double now_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}
int main(void) {
    const int sizes[] = BENCH_SIZES;
    const int count = sizes[0];
    const size_t elements = (size_t)count * STEP;
    int *data = malloc(elements * sizeof(*data));
    int *sequential = malloc((size_t)count * sizeof(*sequential));
    int *shuffled = malloc((size_t)count * sizeof(*shuffled));
    if (!data || !sequential || !shuffled) {
        fprintf(stderr, "Не удалось выделить 544 МиБ для замера.\n");
        free(data); free(sequential); free(shuffled);
        return 1;
    }
    /* Initialization, page faults and shuffling are outside the timed region. */
    for (size_t i = 0; i < elements; i++) data[i] = (int)(i % 17);
    int expected = 0;
    for (int i = 0; i < count; i++) {
        sequential[i] = shuffled[i] = i * STEP;
        expected += data[sequential[i]];
    }
    for (int i = count - 1; i > 0; i--) {
        const int j = (int)(random_u32() % (uint32_t)(i + 1));
        const int tmp = shuffled[i]; shuffled[i] = shuffled[j]; shuffled[j] = tmp;
    }
    int a = 0, b = 0;
    for (int w = 0; w < BENCH_WARMUP; w++) {
        a = fn_a(data, sequential, count); b = fn_b(data, shuffled, count);
    }
    printf("{\"samples\":[");
    for (int r = 0; r < BENCH_REPEATS; r++) {
        double ta, tb, start;
        if (r % 2 == 0) {
            start = now_ms(); a = fn_a(data, sequential, count); ta = now_ms() - start;
            start = now_ms(); b = fn_b(data, shuffled, count); tb = now_ms() - start;
        } else {
            start = now_ms(); b = fn_b(data, shuffled, count); tb = now_ms() - start;
            start = now_ms(); a = fn_a(data, sequential, count); ta = now_ms() - start;
        }
        if (a != expected || b != expected) {
            fprintf(stderr, "Сумма не совпадает с ожидаемой.\n");
            free(data); free(sequential); free(shuffled);
            return 2;
        }
        printf("%s{\"a\":%.6f,\"b\":%.6f}", r ? "," : "", ta, tb);
    }
    printf("],\"check\":{\"a\":%d,\"b\":%d}}\n", a, b);
    free(data); free(sequential); free(shuffled);
    return 0;
}
