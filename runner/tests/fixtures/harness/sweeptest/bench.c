#include <stdio.h>
#include <stdlib.h>
#include <time.h>

extern double fn_a(const double *data, int n);

static double now_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

static int cmp_double(const void *a, const void *b) {
    double da = *(const double *)a;
    double db = *(const double *)b;
    return (da > db) - (da < db);
}

int main(void) {
    const int sizes[] = BENCH_SIZES;
    const int nsizes = BENCH_NSIZES;
    double times[BENCH_REPEATS];
    double sink = 0;

    /* Инварианты протокола sweep — сохраняйте их при копировании файла под
     * новый sweep-харнесс, иначе кривая задержки кэша станет нечестной:
     *  1. Один размер за раз: массив заново выделяется и заполняется перед
     *     каждым size, чтобы прогон на большом size не унаследовал кэш,
     *     прогретый предыдущим маленьким size.
     *  2. BENCH_WARMUP прогонов на каждый size отброшены (не попали в
     *     times), как и в A/B — первый прогон меряет холодный кэш и page
     *     faults, а не сам алгоритм.
     *  3. Из BENCH_REPEATS сырых замеров на size берётся медиана (сортировкой
     *     и взятием среднего элемента) — та же причина, что и в A/B, но
     *     редукция происходит здесь, в C, а не в Python: наружу для каждой
     *     точки нужно одно число, а не набор сэмплов, sweep не парный.
     */
    printf("{\"series\":[");
    for (int i = 0; i < nsizes; i++) {
        int n = sizes[i];
        double *data = malloc((size_t)n * sizeof(double));
        for (int j = 0; j < n; j++) data[j] = (double)(j % 17) * 0.5;

        for (int w = 0; w < BENCH_WARMUP; w++) sink += fn_a(data, n);

        for (int r = 0; r < BENCH_REPEATS; r++) {
            double t0 = now_ms();
            sink += fn_a(data, n);
            double t1 = now_ms();
            times[r] = t1 - t0;
        }
        qsort(times, BENCH_REPEATS, sizeof(double), cmp_double);
        double ms = times[BENCH_REPEATS / 2];
        printf("%s{\"size\":%d,\"ms\":%.6f,\"ms_per_element\":%.9f}",
               i ? "," : "", n, ms, ms / (double)n);
        free(data);
    }
    printf("],\"sink\":%.6f}\n", sink);
    return 0;
}
