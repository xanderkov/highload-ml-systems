double touch(const double *data, int n) {
    double s = 0;
    for (int i = 0; i < n; i++) s += data[i];
    return s;
}
