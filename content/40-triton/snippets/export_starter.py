"""Перенос widemodel из python backend в libtorch.

Харнесс вызывает export(model, path) с моделью widemodel и путём, куда
сохранить TorchScript-файл, кладёт файл в репозиторий как 1/model.pt и
загружает модель в Triton с конфигом CONFIG.

Контракт:
- export сохраняет модель в TorchScript (torch.jit.trace или torch.jit.script);
- модель должна принимать батч любого размера от 1 до max_batch_size;
- вход называется INPUT__0, выход — OUTPUT__0: так их называет стенд.
"""
import torch

CONFIG = """
# Сейчас: python backend. Переведите конфиг на libtorch.
backend: "python"
max_batch_size: 32
input [ { name: "INPUT__0" data_type: TYPE_FP32 dims: [ 3, 64, 64 ] } ]
output [ { name: "OUTPUT__0" data_type: TYPE_FP32 dims: [ 10 ] } ]
instance_group [ { count: 1 kind: KIND_CPU } ]
dynamic_batching { }
"""


def export(model: torch.nn.Module, path: str) -> None:
    # Сейчас модель никуда не сохраняется.
    pass
