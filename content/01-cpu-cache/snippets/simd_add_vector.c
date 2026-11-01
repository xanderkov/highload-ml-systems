// a = [1, 2, 3, 4, ...], b = [5, 6, 7, 8, ...]
// out = [6, 8, 10, 12, ...]
void add_arrays(const int *a, const int *b,
                int *restrict out, int n) {
    for (int i = 0; i < n; i++) {
        out[i] = a[i] + b[i];
    }
}
