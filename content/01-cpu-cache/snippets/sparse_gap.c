#include <stddef.h>
#include <string.h>

#define GAP_BYTES 0  // промежуток между единицами, в байтах

enum { ONES = 64, REPEATS = 65536 };
#define STEP_INTS (1 + GAP_BYTES / sizeof(int))
#define ARRAY_INTS ((ONES - 1) * STEP_INTS + 1)

static void prepare(int *a) {
    memset(a, 0, ARRAY_INTS * sizeof(int));
    for (size_t i = 0; i < ONES; i++)
        a[i * STEP_INTS] = 1;
}

static int measure(const volatile int *a) {
    int total = 0;
    for (int repeat = 0; repeat < REPEATS; repeat++)
        for (size_t i = 0; i < ONES; i++)
            total += a[i * STEP_INTS];
    return total;
}
