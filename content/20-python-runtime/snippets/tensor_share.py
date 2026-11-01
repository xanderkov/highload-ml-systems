import torch

N_KEYS = 1_000_000


def build_dict() -> dict[str, tuple[int, float]]:
    """Тот же «токенайзер», что в крючке: миллион маленьких Python-объектов."""
    return {f"tok{i}": (i, -(i % 5000) / 100.0) for i in range(N_KEYS)}


def read_dict(data, start: float, stop: float) -> float:
    """Читает записи с доли start по долю stop от всех ключей."""
    total = 0.0
    for i in range(int(N_KEYS * start), int(N_KEYS * stop)):
        token_id, score = data[f"tok{i}"]
        total += token_id + score
    return total


def build_tensor(n_bytes: int) -> torch.Tensor:
    """«Веса»: float32-тензор того же размера в байтах, что и словарь."""
    generator = torch.Generator().manual_seed(0)
    return torch.rand(n_bytes // 4, generator=generator)


def read_tensor(weights: torch.Tensor, start: float, stop: float) -> float:
    """Читает элементы с доли start по долю stop — каждый байт storage."""
    n = weights.numel()
    return float(weights[int(n * start) : int(n * stop)].sum())
