#include <stdlib.h>

/* Тайлинг по всем трём индексам. Идея: не считать элемент результата целиком
   за один проход, а разбить все три цикла на блоки TILE x TILE и считать
   частичные суммы блоками. Внутри блока помещаются три плитки — по одной от
   a, b и c, 3 * 64 * 64 * 8 = 96 КБ, — то есть работа идёт из кэша, а не из
   памяти.

   Порядок блоков ii, kk, jj выбран так, чтобы внутренний цикл шёл по j:
   и b, и c обходятся по соседним адресам подряд. Побочный эффект: этот цикл
   больше не редукция в скаляр, поэтому компилятор его ещё и векторизует —
   посмотрите команду компиляции под результатом.

   Порядок сложений по k при этом сохраняется тот же, что и в наивной версии
   (k растёт монотонно), так что контрольная сумма совпадает. */

#define TILE 64

static inline int min_int(int x, int y) { return x < y ? x : y; }

double matmul(const double *a, const double *b, int n) {
    double *c = calloc((size_t)n * (size_t)n, sizeof(double));
    if (c == NULL) return 0.0;

    for (int ii = 0; ii < n; ii += TILE) {
        const int imax = min_int(ii + TILE, n);
        for (int kk = 0; kk < n; kk += TILE) {
            const int kmax = min_int(kk + TILE, n);
            for (int jj = 0; jj < n; jj += TILE) {
                const int jmax = min_int(jj + TILE, n);
                for (int i = ii; i < imax; i++)
                    for (int k = kk; k < kmax; k++) {
                        const double aik = a[(size_t)i * n + k];
                        for (int j = jj; j < jmax; j++)
                            c[(size_t)i * n + j] += aik * b[(size_t)k * n + j];
                    }
            }
        }
    }

    double total = 0.0;
    for (size_t t = 0; t < (size_t)n * (size_t)n; t++) total += c[t];
    free(c);
    return total;
}
