"""Модель с тяжёлыми весами для подглав 2–6 раздела «Наивный сервис».

Вход тот же, что у tinymodel: (N, 3, 64, 64). Внутри — большие линейные
слои, около 112 МиБ весов float32. На CPU такая модель упирается не в
вычисления, а в чтение весов из памяти: при батче из одного все веса
читаются ради одного элемента. Свёрточная tinymodel, наоборот, упирается в
вычисления, и батч на CPU ей почти не помогает (подглава 2).
"""
import torch
from torch import nn

WIDTH = 2048


def make_model(seed: int = 0) -> nn.Module:
    torch.manual_seed(seed)
    model = nn.Sequential(
        nn.Flatten(),
        nn.Linear(3 * 64 * 64, WIDTH), nn.ReLU(),
        nn.Linear(WIDTH, WIDTH), nn.ReLU(),
        nn.Linear(WIDTH, 10),
    )
    return model.eval()
