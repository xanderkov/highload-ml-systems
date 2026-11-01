double total(const double *data, int n) {
    double s = 0;
    for (int step = 0; step < 16; step++)
        for (int i = step; i < n; i += 16) s += data[i];
    return s;
}
