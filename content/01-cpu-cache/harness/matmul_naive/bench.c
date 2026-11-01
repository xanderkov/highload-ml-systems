#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
extern void fn_a(const double *, const double *, double *, int);
extern void fn_b(const double *, const double *, double *, int);
static double now_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}
int main(void) {
    const int sizes[] = BENCH_SIZES;
    const int n = sizes[0];
    double *a = malloc(n*n*sizeof(double)), *b = malloc(n*n*sizeof(double));
    double *out = malloc(n*n*sizeof(double)), *expected = malloc(n*n*sizeof(double));
    if (!a || !b || !out || !expected) return 1;
    for (int i=0; i<n; i++) for (int j=0; j<n; j++) {
        a[i*n+j] = ((i+j)%16)/16.0;
        b[i*n+j] = ((i+j)%8)/8.0;
        int sum = 0;
        for (int k=0; k<16; k++) sum += ((i+k)%16)*((k+j)%8);
        expected[i*n+j] = sum*(n/16)/128.0;
    }
    void (*functions[])(const double *, const double *, double *, int) = {fn_a,fn_b};
    printf("{\"samples\":[");
    for (int r=-BENCH_WARMUP; r<BENCH_REPEATS; r++) {
        double times[2];
        for (int offset=0; offset<2; offset++) {
            int k=(r+BENCH_WARMUP+offset)%2;
            for (int i=0;i<n*n;i++) out[i]=NAN;
            double start=now_ms();
            functions[k](a,b,out,n);
            times[k]=now_ms()-start;
            for (int i=0;i<n*n;i++) if(out[i]!=expected[i]) {
                fprintf(stderr,"Результат не совпадает с ожидаемым.\n");return 2;
            }
        }
        if(r>=0) printf("%s{\"a\":%.6f,\"b\":%.6f}",r?",":"",times[0],times[1]);
    }
    printf("],\"check\":{\"a\":1,\"b\":1}}\n");
    free(a);free(b);free(out);free(expected);
    return 0;
}
