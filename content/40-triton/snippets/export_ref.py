"""Эталон: TorchScript через torch.jit.trace и конфиг pytorch_libtorch."""
import torch

CONFIG = """
platform: "pytorch_libtorch"
max_batch_size: 32
input [ { name: "INPUT__0" data_type: TYPE_FP32 dims: [ 3, 64, 64 ] } ]
output [ { name: "OUTPUT__0" data_type: TYPE_FP32 dims: [ 10 ] } ]
instance_group [ { count: 1 kind: KIND_CPU } ]
parameters: { key: "INTRA_OP_THREAD_COUNT" value: { string_value: "3" } }
dynamic_batching { }
"""


def export(model: torch.nn.Module, path: str) -> None:
    model.eval()
    # Пример входа задаёт только типы и ранг: у widemodel нет операций,
    # зависящих от размера батча, поэтому трасса работает с любым батчем.
    with torch.no_grad():
        torch.jit.trace(model, torch.zeros(2, 3, 64, 64)).save(path)
