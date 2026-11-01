# Копия content/20-python-runtime/harness/_lib/tinymodel.py: _lib разделов независимы (спека §5.4).
"""Маленький CNN для демонстраций: вход (N, 3, 64, 64), веса детерминированы seed."""
import torch
from torch import nn


def make_model(seed: int = 0) -> nn.Module:
    torch.manual_seed(seed)
    model = nn.Sequential(
        nn.Conv2d(3, 32, 3, padding=1), nn.ReLU(),
        nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(),
        nn.MaxPool2d(2),
        nn.Conv2d(64, 64, 3, padding=1), nn.ReLU(),
        nn.AdaptiveAvgPool2d(1), nn.Flatten(),
        nn.Linear(64, 10),
    )
    return model.eval()


def make_input(batch: int, seed: int = 0) -> torch.Tensor:
    g = torch.Generator().manual_seed(seed)
    return torch.randn(batch, 3, 64, 64, generator=g)
