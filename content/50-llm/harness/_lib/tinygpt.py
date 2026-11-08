"""Крошечная GPT раздела «LLM»: случайные веса, жадная генерация, KV-кэш.

Модель ничего не знает о языке — веса случайные, «текст» бессмысленный. Зато
цикл генерации виден целиком:

- prefill(prompt) прогоняет весь промпт за один вызов, возвращает первый
  сгенерированный токен и KV-кэш запроса (ключи и значения всех слоёв);
- decode_step(batch, last) делает один шаг для всех строк KVBatch: подаёт
  последний токен каждой строки, дописывает его K/V в кэш строки и
  возвращает следующий токен каждой строки.

KVBatch держит кэши нескольких запросов разной длины в одном тензоре с
паддингом справа; add() добавляет строку, keep() оставляет выбранные строки.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import torch
import torch.nn.functional as F
from torch import nn

GROW = 64  # на сколько позиций растёт тензор KVBatch, когда место кончилось


@dataclass(frozen=True)
class Config:
    n_layer: int = 8
    d_model: int = 512
    n_head: int = 8
    vocab: int = 4096
    max_len: int = 1024


DEFAULT = Config()

# KV одного запроса: (K, V), каждый [n_layer, n_head, длина, head_dim].
KV = tuple[torch.Tensor, torch.Tensor]


def kv_bytes_per_token(cfg: Config = DEFAULT) -> int:
    """K и V каждого слоя, float32."""
    return 2 * cfg.n_layer * cfg.d_model * 4


class KVBatch:
    """KV-кэши нескольких запросов: строка — запрос, паддинг справа.

    Тензоры выделяются с запасом по строкам и по длине: add() пишет только
    новую строку, keep() двигает только те строки, что сменили номер, а шаг
    работает с представлением первых len(self) строк без копирования.
    """

    def __init__(self) -> None:
        self.k: torch.Tensor | None = None  # [n_layer, cap_rows, n_head, cap_len, head_dim]
        self.v: torch.Tensor | None = None
        self.lengths: list[int] = []

    def __len__(self) -> int:
        return len(self.lengths)

    def _grow(self, dim: int, extra: int) -> None:
        pad = list(self.k.shape)
        pad[dim] = extra
        # Кэш растёт и внутри decode_step (inference mode); тензоры кэша должны
        # остаться обычными, иначе add() снаружи не сможет писать в них.
        with torch.inference_mode(False):
            self.k = torch.cat([self.k, self.k.new_zeros(pad)], dim=dim)
            self.v = torch.cat([self.v, self.v.new_zeros(pad)], dim=dim)

    def _ensure(self, need: int) -> None:
        """Длины хватает на need позиций."""
        cap = self.k.shape[3]
        if need > cap:
            self._grow(3, math.ceil((need - cap) / GROW) * GROW)

    def add(self, kv: KV) -> int:
        """Добавляет KV одного запроса последней строкой; возвращает её индекс."""
        k, v = kv
        n = k.shape[2]
        if self.k is None:
            shape = (k.shape[0], 4, k.shape[1], math.ceil(max(n, 1) / GROW) * GROW, k.shape[3])
            self.k, self.v = k.new_zeros(shape), v.new_zeros(shape)
        self._ensure(n)
        row = len(self.lengths)
        if row == self.k.shape[1]:
            self._grow(1, self.k.shape[1])
        self.k[:, row, :, :n] = k
        self.v[:, row, :, :n] = v
        self.lengths.append(n)
        return row

    def keep(self, rows: list[int]) -> None:
        """Оставляет строки rows в этом порядке (остальные — освобождаются)."""
        rows = list(rows)
        for r in rows:
            if not 0 <= r < len(self.lengths):
                raise IndexError(f"keep: строки {r} нет, в батче {len(self.lengths)} строк")
        if rows == sorted(set(rows)):
            # Частый случай — убрали закончившиеся, порядок прежний: строки
            # только сдвигаются вверх, копируем лишь сдвинутые.
            for new, old in enumerate(rows):
                if new != old:
                    self.k[:, new] = self.k[:, old]
                    self.v[:, new] = self.v[:, old]
        elif rows:
            index = torch.tensor(rows, dtype=torch.long)
            self.k[:, :len(rows)] = self.k.index_select(1, index)
            self.v[:, :len(rows)] = self.v.index_select(1, index)
        self.lengths = [self.lengths[r] for r in rows]

    def nbytes(self) -> int:
        """Полезные байты кэша (без паддинга и запаса): сумма длин × байт на токен."""
        if self.k is None:
            return 0
        per_token = 2 * self.k.shape[0] * self.k.shape[2] * self.k.shape[4] * self.k.element_size()
        return sum(self.lengths) * per_token


class Block(nn.Module):
    def __init__(self, cfg: Config):
        super().__init__()
        self.n_head = cfg.n_head
        self.ln1 = nn.LayerNorm(cfg.d_model)
        self.qkv = nn.Linear(cfg.d_model, 3 * cfg.d_model)
        self.proj = nn.Linear(cfg.d_model, cfg.d_model)
        self.ln2 = nn.LayerNorm(cfg.d_model)
        self.fc = nn.Linear(cfg.d_model, 4 * cfg.d_model)
        self.out = nn.Linear(4 * cfg.d_model, cfg.d_model)

    def _heads(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        b, t, d = x.shape
        q, k, v = self.qkv(self.ln1(x)).split(d, dim=2)
        shape = (b, t, self.n_head, d // self.n_head)
        return (q.view(shape).transpose(1, 2), k.view(shape).transpose(1, 2),
                v.view(shape).transpose(1, 2))

    def _finish(self, x: torch.Tensor, att: torch.Tensor) -> torch.Tensor:
        b, _, t, _ = att.shape
        x = x + self.proj(att.transpose(1, 2).reshape(b, t, -1))
        return x + self.out(F.gelu(self.fc(self.ln2(x))))

    def full(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Вся последовательность сразу (causal); возвращает выход и K, V."""
        q, k, v = self._heads(x)
        att = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        return self._finish(x, att), k, v

    def step(self, x: torch.Tensor, kc: torch.Tensor, vc: torch.Tensor, pos: torch.Tensor,
             mask: torch.Tensor) -> torch.Tensor:
        """Один новый токен на строку; K/V пишутся в кэш строки на позицию pos."""
        q, k, v = self._heads(x)  # [rows, heads, 1, hd]
        rows = torch.arange(x.shape[0])
        kc[rows, :, pos] = k[:, :, 0]
        vc[rows, :, pos] = v[:, :, 0]
        span = int(pos.max()) + 1
        att = F.scaled_dot_product_attention(q, kc[:, :, :span], vc[:, :, :span], attn_mask=mask[:, None, None, :span])
        return self._finish(x, att)


class TinyGPT(nn.Module):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.tok = nn.Embedding(cfg.vocab, cfg.d_model)
        self.pos = nn.Embedding(cfg.max_len, cfg.d_model)
        self.blocks = nn.ModuleList(Block(cfg) for _ in range(cfg.n_layer))
        self.ln = nn.LayerNorm(cfg.d_model)
        self.head = nn.Linear(cfg.d_model, cfg.vocab, bias=False)

    def _logits(self, tokens: list[int]) -> tuple[torch.Tensor, KV]:
        if not tokens:
            raise ValueError("пустой промпт")
        if len(tokens) > self.cfg.max_len:
            raise ValueError(f"промпт длиннее {self.cfg.max_len} токенов")
        idx = torch.tensor([tokens])
        x = self.tok(idx) + self.pos(torch.arange(len(tokens)))[None]
        ks, vs = [], []
        for block in self.blocks:
            x, k, v = block.full(x)
            ks.append(k[0])
            vs.append(v[0])
        return self.head(self.ln(x[0, -1])), (torch.stack(ks), torch.stack(vs))

    @torch.inference_mode()
    def prefill(self, prompt: list[int]) -> tuple[int, KV]:
        logits, kv = self._logits(prompt)
        return int(logits.argmax()), kv

    @torch.inference_mode()
    def decode_step(self, batch: KVBatch, last: torch.Tensor) -> torch.Tensor:
        if len(batch) == 0 or last.shape != (len(batch),):
            raise ValueError(f"last должен быть тензором из {len(batch)} токенов — по одному на строку батча")
        pos = torch.tensor(batch.lengths)
        if int(pos.max()) >= self.cfg.max_len:
            raise ValueError(f"запрос длиннее {self.cfg.max_len} токенов")
        batch._ensure(int(pos.max()) + 1)
        n = len(batch)
        mask = torch.arange(batch.k.shape[3])[None, :] <= pos[:, None]
        x = (self.tok(last) + self.pos(pos))[:, None]
        for i, block in enumerate(self.blocks):
            x = block.step(x, batch.k[i, :n], batch.v[i, :n], pos, mask)
        batch.lengths = [n + 1 for n in batch.lengths]
        return self.head(self.ln(x[:, 0])).argmax(dim=-1)


def make_model(cfg: Config = DEFAULT, seed: int = 0) -> TinyGPT:
    with torch.random.fork_rng():  # не трогаем глобальный генератор вызывающего
        torch.manual_seed(seed)
        model = TinyGPT(cfg)
    gen = torch.Generator().manual_seed(seed)
    with torch.no_grad():
        for name, p in model.named_parameters():
            if name.endswith("bias") or ".ln" in name or name.startswith("ln."):
                continue
            std = 1.0 if p.dim() == 2 and ("tok" in name or "pos" in name) else 1 / math.sqrt(p.shape[-1])
            p.copy_(torch.randn(p.shape, generator=gen) * std)
    return model.eval().requires_grad_(False)


def generate_alone(model: TinyGPT, prompt: list[int], n: int) -> list[int]:
    """Эталон: один запрос, KV-кэш, без батча."""
    tok, kv = model.prefill(prompt)
    out = [tok]
    batch = KVBatch()
    batch.add(kv)
    while len(out) < n:
        out.append(int(model.decode_step(batch, torch.tensor([out[-1]]))[0]))
    return out


@torch.inference_mode()
def generate_nocache(model: TinyGPT, prompt: list[int], n: int) -> list[int]:
    """Без кэша: каждый шаг заново прогоняет весь префикс."""
    seq = list(prompt)
    out: list[int] = []
    for _ in range(n):
        logits, _ = model._logits(seq)
        out.append(int(logits.argmax()))
        seq.append(out[-1])
    return out
