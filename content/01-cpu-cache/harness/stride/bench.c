#include <stdio.h>
#include <stdlib.h>
#include <time.h>

extern double fn_a(const long *next, int n, long steps);

/* Одно и то же число обращений на каждом размере: только тогда точки кривой
   сравнимы между собой, а ms_per_element читается как средняя цена одного
   обращения. Если бы число шагов зависело от размера, форма кривой была бы
   формой этой зависимости, а не свойством памяти. */
#define BENCH_STEPS 4000000L

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

/* Алгоритм Саттоло: перестановка, состоящая ровно из одного цикла длины n.
   Обычная тасовка Фишера — Йетса дала бы несколько коротких циклов, и обход
   застрял бы в маленьком куске массива, меряя кэш вместо рабочего набора.

   Обход именно случайный, а не последовательный: последовательный проход
   предсказывает префетчер, и вместо задержки памяти мы бы мерили её
   пропускную способность — кривая вышла бы почти плоской. Про префетчер
   отдельный замер дальше в разделе. */
static void build_cycle(long *next, int n) {
    unsigned long seed = 0x9E3779B97F4A7C15UL;
    for (int i = 0; i < n; i++) next[i] = i;
    for (int i = n - 1; i > 0; i--) {
        seed = seed * 6364136223846793005UL + 1442695040888963407UL;
        int j = (int)((seed >> 33) % (unsigned long)i);
        long tmp = next[i];
        next[i] = next[j];
        next[j] = tmp;
    }
}

int main(void) {
    const int sizes[] = BENCH_SIZES;
    const int nsizes = BENCH_NSIZES;
    double times[BENCH_REPEATS];
    double sink = 0;

    /* Инварианты протокола sweep (см. runner/app/jobs.py::_parse_sweep_output):
     *  1. Один размер за раз, массив выделяется и перемешивается заново —
     *     иначе большой размер унаследовал бы кэш, прогретый предыдущим.
     *  2. BENCH_WARMUP прогонов на каждый размер отброшены.
     *  3. Наружу уходит ровно одна строка JSON, в ней ровно BENCH_NSIZES
     *     точек, у каждой есть size и ms_per_element.
     */
    printf("{\"series\":[");
    for (int i = 0; i < nsizes; i++) {
        const int n = sizes[i];
        long *next = malloc((size_t)n * sizeof(long));
        if (next == NULL) {
            fprintf(stderr, "не хватило памяти на %d элементов\n", n);
            return 1;
        }
        build_cycle(next, n);

        for (int w = 0; w < BENCH_WARMUP; w++) sink += fn_a(next, n, BENCH_STEPS);

        for (int r = 0; r < BENCH_REPEATS; r++) {
            double t0 = now_ms();
            sink += fn_a(next, n, BENCH_STEPS);
            double t1 = now_ms();
            times[r] = t1 - t0;
        }
        qsort(times, BENCH_REPEATS, sizeof(double), cmp_double);
        const double ms = times[BENCH_REPEATS / 2];
        printf("%s{\"size\":%d,\"ms\":%.6f,\"ms_per_element\":%.9f}",
               i ? "," : "", n, ms, ms / (double)BENCH_STEPS);
        free(next);
    }
    printf("],\"sink\":%.6f}\n", sink);
    return 0;
}
