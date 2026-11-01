#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

extern int fn_a(const int *, int);
extern int fn_b(const int *, int);

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
    int *mixed = malloc((size_t)count * sizeof(*mixed));
    if (!mixed) {
        fprintf(stderr, "Не удалось выделить память для массивов.\n");
        free(mixed);
        return 1;
    }
    /* Fixed seed, identical input for both variants; initialization is not timed.
       With count=1048576 and each term <=1000, all sums fit in signed int. */
    int expected = 0;
    for (int i = 0; i < count; i++) {
        const int sample = (int)(random_u32() % 200);
        const int value = sample < 100 ? -(sample + 1) : sample - 99;
        mixed[i] = value;
        if (value > 0) expected += 1000 / value;
    }
    int (*functions[])(const int *, int) = {fn_a, fn_b};
    const int *inputs[] = {mixed, mixed};
    int checks[2] = {0};
    for (int w = 0; w < BENCH_WARMUP; w++) {
        for (int k = 0; k < 2; k++) checks[k] = functions[k](inputs[k], count);
    }
    printf("{\"samples\":[");
    for (int r = 0; r < BENCH_REPEATS; r++) {
        double times[2];
        /* Rotate the execution order so no variant is always measured first. */
        for (int offset = 0; offset < 2; offset++) {
            const int k = (r + offset) % 2;
            const double start = now_ms();
            checks[k] = functions[k](inputs[k], count);
            times[k] = now_ms() - start;
            if (checks[k] != expected) {
                fprintf(stderr, "Сумма не совпадает с ожидаемой.\n");
                free(mixed);
                return 2;
            }
        }
        printf("%s{\"a\":%.6f,\"b\":%.6f}", r ? "," : "", times[0], times[1]);
    }
    printf("],\"check\":{\"a\":%d,\"b\":%d}}\n", checks[0], checks[1]);
    free(mixed);
    return 0;
}
