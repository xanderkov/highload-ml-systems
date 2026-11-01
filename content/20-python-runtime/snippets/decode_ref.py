"""Граница запроса: клиент кодирует изображение, сервер декодирует его в тензор.

img — np.ndarray uint8 формы (224, 224, 3) (высота, ширина, каналы).
decode должен вернуть torch.Tensor float32 формы (3, 224, 224)
со значениями img / 255.
"""
import numpy as np
import torch


def encode(img: np.ndarray) -> bytes:
    """Клиент: сырые байты пикселей, 150 528 байт, без разбора и форматирования."""
    return img.tobytes()


def decode(body: bytes) -> torch.Tensor:
    """Сервер: тензор для модели из тела запроса."""
    # Вид на body без копии: numpy-массив смотрит прямо в байты запроса.
    # Он только для чтения, как и сами bytes.
    pixels = np.frombuffer(body, dtype=np.uint8).reshape(224, 224, 3)
    # Тензор нужного dtype и формы; numpy() — его же память в виде массива.
    out = torch.empty((3, 224, 224), dtype=torch.float32)
    # Единственная копия: uint8 → float32 сразу в порядке (каналы, высота, ширина).
    out.numpy()[...] = pixels.transpose(2, 0, 1)
    return out.div_(255)
