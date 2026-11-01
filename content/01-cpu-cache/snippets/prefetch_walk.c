/* Предсказуемый обход с постоянным шагом. В отличие от обхода по цепочке,
   здесь адрес следующего чтения известен заранее — процессор может начать
   его подтягивать, не дожидаясь предыдущего. */
double walk_stride(const double *data, long n, long stride) {
    double total = 0.0;
    for (long i = 0; i < n; i += stride) total += data[i];
    return total;
}
