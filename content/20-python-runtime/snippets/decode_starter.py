"""Граница запроса: клиент кодирует изображение, сервер декодирует его в тензор.

img — np.ndarray uint8 формы (224, 224, 3) (высота, ширина, каналы).
decode должен вернуть torch.Tensor float32 формы (3, 224, 224)
со значениями img / 255.
"""
import json

import numpy as np
import torch


def encode(img: np.ndarray) -> bytes:
    """Клиент: тело запроса. Сейчас — JSON со вложенными списками чисел."""
    return json.dumps(img.tolist()).encode()


def decode(body: bytes) -> torch.Tensor:
    """Сервер: тензор для модели из тела запроса."""
    return torch.tensor(json.loads(body), dtype=torch.float32).permute(2, 0, 1) / 255
