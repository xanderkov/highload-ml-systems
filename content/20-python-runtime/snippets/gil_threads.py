"""Три нагрузки одинакового «размера»: одна задача — примерно 40 мс на одном ядре.

Харнесс делит TASKS задач между 1, 2 и 4 потоками и меряет общее время.
"""
import numpy as np
import torch

from tinymodel import make_input, make_model

TASKS = 8

_a = np.random.default_rng(0).random((256, 256))
_model = make_model()
_x = make_input(1)


def pure_python() -> float:
    """Цикл на байткоде: каждую инструкцию исполняет интерпретатор под GIL."""
    total = 0
    for i in range(800_000):
        total += i * i % 7
    return float(total)


def numpy_matmul() -> float:
    """Умножение матриц 256×256: внутри BLAS, GIL на время вызова отпущен."""
    total = 0.0
    for _ in range(80):
        total += float((_a @ _a)[0, 0])
    return total


def torch_infer() -> float:
    """Инференс маленькой CNN по одному входу: ядра torch тоже отпускают GIL."""
    # Своё значение числа потоков OpenMP у каждого потока Python: 1, чтобы
    # параллельность давали только наши потоки, а не torch внутри вызова.
    torch.set_num_threads(1)
    total = 0.0
    with torch.inference_mode():
        for _ in range(12):
            total += float(_model(_x)[0, 0])
    return total
