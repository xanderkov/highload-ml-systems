import numpy as np

# A и B — одинаковые в обоих замерах матрицы 384 × 384, float64.
# out — заранее выделенная матрица результата.
def multiply(A, B, out):
    np.matmul(A, B, out=out)
