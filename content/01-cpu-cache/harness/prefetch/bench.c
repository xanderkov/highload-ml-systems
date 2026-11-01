#include <stdio.h>
#include <stdlib.h>
#include <time.h>

extern double fn_a(const double *data, long n, long stride);

/* Массив фиксирован и заведомо больше любого кэша: в этом замере меняется
   только шаг обхода, а размер рабочего набора обязан оставаться постоянным —
   иначе кривая смешала бы два эффекта сразу. 33554432 double = 256 МБ.
   Меньше брать нельзя: на 64 МБ массив частично оседает в кэше последнего
   уровня современных машин, и кривая выходила плоской и немонотонной. */
#define BENCH_ELEMENTS 33554432L

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
    const int sizes[] = BENCH_SIZES; /* здесь size — это шаг обхода в элементах */
    const int nsizes = BENCH_NSIZES;
    double times[BENCH_REPEATS];
    double sink = 0;

    double *data = malloc((size_t)BENCH_ELEMENTS * sizeof(double));
    if (data == NULL) {
        fprintf(stderr, "не хватило памяти на %ld элементов\n", BENCH_ELEMENTS);
        return 1;
    }
    for (long i = 0; i < BENCH_ELEMENTS; i++) data[i] = (double)(i % 17) * 0.5;

    /* Инварианты те же, что в harness/stride/bench.c. Отличие одно: нормировка
       идёт не на число шагов цикла, а на число реально прочитанных элементов
       (BENCH_ELEMENTS / stride) — вопрос замера в том, сколько стоит одно
       обращение при данном шаге, а не сколько стоит проход целиком. */
    printf("{\"series\":[");
    for (int i = 0; i < nsizes; i++) {
        const long stride = sizes[i];
        const double touched = (double)((BENCH_ELEMENTS + stride - 1) / stride);

        for (int w = 0; w < BENCH_WARMUP; w++) sink += fn_a(data, BENCH_ELEMENTS, stride);

        for (int r = 0; r < BENCH_REPEATS; r++) {
            double t0 = now_ms();
            sink += fn_a(data, BENCH_ELEMENTS, stride);
            double t1 = now_ms();
            times[r] = t1 - t0;
        }
        qsort(times, BENCH_REPEATS, sizeof(double), cmp_double);
        const double ms = times[BENCH_REPEATS / 2];
        printf("%s{\"size\":%ld,\"ms\":%.6f,\"ms_per_element\":%.9f}",
               i ? "," : "", stride, ms, ms / touched);
    }
    printf("],\"sink\":%.6f}\n", sink);
    free(data);
    return 0;
}
