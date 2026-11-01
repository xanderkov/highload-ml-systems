#include <stddef.h>

/* Build the same file with MATRIX_COLUMNS=0 (rows) or 1 (columns).
   The compiler selects native inline assembly; it does not generate the loop.
   As in the course harness, the final sum must fit in int. */
#ifndef MATRIX_COLUMNS
#define MATRIX_COLUMNS 0
#endif

int matrix_sum(const int *a, int n) {
    if (n <= 0) return 0;
    const size_t count = (size_t)n * (size_t)n;
    const size_t step = (size_t)n;
    const size_t wrap = count - 1;
    size_t index, processed;
    int sum, value;

#if defined(__x86_64__)
    /* GCC's default AT&T syntax: source first, destination second.
       Early-clobber outputs prevent aliasing with inputs used by the loop. */
    __asm__ volatile (
        "movl $0, %k[sum]\n\t"
        "movq $0, %[index]\n\t"
        "movq $0, %[processed]\n\t"
        "1:\n\t"
        "movl (%[base], %[index], 4), %k[value]\n\t"
        "addl %k[value], %k[sum]\n\t"
#if MATRIX_COLUMNS
        "addq %[step], %[index]\n\t"
        "cmpq %[count], %[index]\n\t"
        "jb 2f\n\t"
        "subq %[wrap], %[index]\n\t"
        "2:\n\t"
#else
        "addq $1, %[index]\n\t"
#endif
        "addq $1, %[processed]\n\t"
        "cmpq %[count], %[processed]\n\t"
        "jne 1b\n\t"
        : [sum] "=&r" (sum), [value] "=&r" (value),
          [index] "=&r" (index), [processed] "=&r" (processed)
        : [base] "r" (a), [count] "r" (count),
          [step] "r" (step), [wrap] "r" (wrap)
        : "cc", "memory"
    );
#elif defined(__aarch64__)
    __asm__ volatile (
        "mov %w[sum], wzr\n\t"
        "mov %[index], xzr\n\t"
        "mov %[processed], xzr\n\t"
        "1:\n\t"
        "ldr %w[value], [%[base], %[index], lsl #2]\n\t"
        "add %w[sum], %w[sum], %w[value]\n\t"
#if MATRIX_COLUMNS
        "add %[index], %[index], %[step]\n\t"
        "cmp %[index], %[count]\n\t"
        "b.lo 2f\n\t"
        "sub %[index], %[index], %[wrap]\n\t"
        "2:\n\t"
#else
        "add %[index], %[index], #1\n\t"
#endif
        "add %[processed], %[processed], #1\n\t"
        "cmp %[processed], %[count]\n\t"
        "b.ne 1b\n\t"
        : [sum] "=&r" (sum), [value] "=&r" (value),
          [index] "=&r" (index), [processed] "=&r" (processed)
        : [base] "r" (a), [count] "r" (count),
          [step] "r" (step), [wrap] "r" (wrap)
        : "cc", "memory"
    );
#else
#error "matrix_sum_asm supports only x86-64 and ARM64"
#endif
    return sum;
}
