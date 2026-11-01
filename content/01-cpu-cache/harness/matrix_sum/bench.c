#include <stdio.h>
#include <stdlib.h>
#include <time.h>

extern int fn_a(const int *a, int n);
extern int fn_b(const int *a, int n);

static double now_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

int main(void) {
    const int sizes[] = BENCH_SIZES;
    const int n = sizes[0];
    const size_t total = (size_t)n * (size_t)n;

    int *data = malloc(total * sizeof(*data));
    if (data == NULL) {
        fprintf(stderr, "не хватило памяти на матрицу %d x %d\n", n, n);
        return 1;
    }
    /* Значения детерминированные: два варианта обязаны получить один и тот же
       ответ, иначе сравнивать их время бессмысленно. Период 17 взаимно прост
       с длиной строки, так что строки не совпадают друг с другом.
       При n = 2048 сумма не превышает 16 * 2048 * 2048 и помещается в int. */
    for (size_t i = 0; i < total; i++) data[i] = (int)(i % 17);

    int check_a = 0, check_b = 0;
    for (int w = 0; w < BENCH_WARMUP; w++) { check_a = fn_a(data, n); check_b = fn_b(data, n); }

    /* Инварианты протокола замера (см. runner/app/jobs.py::_parse_output):
     *  1. BENCH_WARMUP прогонов выше отброшены — первый проход по 16 МБ меряет
     *     page faults и холодный кэш, а не порядок обхода.
     *  2. Каждый повтор чередует A и B, а не гоняет их блоками, — иначе
     *     троттлинг и дрейф частоты бьют по одному варианту сильнее.
     *  3. В stdout уходит ровно одна строка JSON с ровно BENCH_REPEATS
     *     замерами: любая лишняя строка или лишний замер — output_error.
     *     Медиану считает Python в measure.ab_result.
     */
    printf("{\"samples\":[");
    for (int r = 0; r < BENCH_REPEATS; r++) {
        double t0 = now_ms(); check_a = fn_a(data, n); double t1 = now_ms();
        double t2 = now_ms(); check_b = fn_b(data, n); double t3 = now_ms();
        printf("%s{\"a\":%.6f,\"b\":%.6f}", r ? "," : "", t1 - t0, t3 - t2);
    }
    printf("],\"check\":{\"a\":%d,\"b\":%d}}\n", check_a, check_b);

    free(data);
    return 0;
}
