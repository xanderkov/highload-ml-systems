#include <stdio.h>
#include <stdlib.h>
#include <time.h>

extern double fn_a(const double *data, int n);
extern double fn_b(const double *data, int n);

static double now_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

int main(void) {
    const int sizes[] = BENCH_SIZES;
    const int n = sizes[0];
    double *data = malloc((size_t)n * sizeof(double));
    for (int i = 0; i < n; i++) data[i] = (double)(i % 17) * 0.5;

    double check_a = 0, check_b = 0;
    for (int w = 0; w < BENCH_WARMUP; w++) { check_a = fn_a(data, n); check_b = fn_b(data, n); }

    /* Инварианты протокола замера — сохраняйте их при копировании этого
     * файла под новый харнесс, иначе измерение станет нечестным:
     *  1. BENCH_WARMUP прогонов выше отброшены (не попали в samples) —
     *     первый прогон меряет холодный кэш и page faults, а не алгоритм.
     *  2. Каждый повтор чередует A и B (interleaved: a, затем b, затем
     *     следующий повтор), а не блоками "все A, потом все B" — иначе
     *     троттлинг/просадка частоты бьёт по одному варианту сильнее.
     *  3. Здесь пишутся только сырые замеры, ровно BENCH_REPEATS штук;
     *     медиану (а не среднее) считает Python в measure.ab_result.
     */
    printf("{\"samples\":[");
    for (int r = 0; r < BENCH_REPEATS; r++) {
        double t0 = now_ms(); check_a = fn_a(data, n); double t1 = now_ms();
        double t2 = now_ms(); check_b = fn_b(data, n); double t3 = now_ms();
        printf("%s{\"a\":%.6f,\"b\":%.6f}", r ? "," : "", t1 - t0, t3 - t2);
    }
    printf("],\"check\":{\"a\":%.17g,\"b\":%.17g}}\n", check_a, check_b);
    free(data);
    return 0;
}
