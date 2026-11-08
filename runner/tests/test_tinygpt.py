"""tinygpt раздела «LLM»: KV-кэш и KVBatch дают те же токены, что генерация в одиночку."""
import os
import sys

import torch

_root = os.environ.get("CONTENT_ROOT", "/content")
sys.path.insert(0, os.path.join(_root, "50-llm", "harness", "_lib"))

import tinygpt  # noqa: E402

PROMPTS = [[1, 2, 3], [5] * 11, list(range(40, 77))]


def model(seed=0):
    torch.manual_seed(1234)  # тесты не зависят от глобального seed
    return tinygpt.make_model(seed=seed)


def test_cached_equals_nocache():
    m = model()
    for p in PROMPTS:
        assert tinygpt.generate_alone(m, p, 32) == tinygpt.generate_nocache(m, p, 32)


def test_generation_is_not_stuck_on_one_token():
    m = model()
    assert len(set(tinygpt.generate_alone(m, PROMPTS[0], 32))) >= 4


def test_batch_equals_alone_with_joins_and_drops():
    m = model()
    jobs = [(p, n) for p, n in zip(
        [[1, 2, 3], [7] * 9, list(range(100, 130)), [3, 1], list(range(200, 205)), [9] * 20],
        [5, 17, 9, 30, 12, 3])]
    expected = [tinygpt.generate_alone(m, p, n) for p, n in jobs]

    batch = tinygpt.KVBatch()
    rows: list[int] = []  # номер запроса в строке батча
    out = {i: [] for i in range(len(jobs))}
    last: list[int] = []
    pending = list(range(len(jobs)))
    while pending or rows:
        if pending:  # по одному новому запросу между шагами
            i = pending.pop(0)
            tok, kv = m.prefill(jobs[i][0])
            assert batch.add(kv) == len(rows)
            rows.append(i)
            last.append(tok)
            out[i].append(tok)
        keep = [r for r, i in enumerate(rows) if len(out[i]) < jobs[i][1]]
        if len(keep) != len(rows):
            keep.reverse()  # порядок строк меняется — индексы должны остаться верными
            batch.keep(keep)
            rows = [rows[r] for r in keep]
            last = [last[r] for r in keep]
        assert len(batch) == len(rows)
        if not rows:
            continue
        nxt = m.decode_step(batch, torch.tensor(last))
        last = nxt.tolist()
        for i, tok in zip(rows, last):
            out[i].append(tok)
    assert [out[i] for i in range(len(jobs))] == expected


def test_deterministic_by_seed():
    a = tinygpt.generate_alone(model(0), PROMPTS[2], 16)
    b = tinygpt.generate_alone(model(0), PROMPTS[2], 16)
    c = tinygpt.generate_alone(model(1), PROMPTS[2], 16)
    assert a == b
    assert a != c


def test_kv_bytes():
    m = model()
    batch = tinygpt.KVBatch()
    for p in PROMPTS:
        batch.add(m.prefill(p)[1])
    cfg = tinygpt.DEFAULT
    assert tinygpt.kv_bytes_per_token(cfg) == 2 * cfg.n_layer * cfg.d_model * 4
    assert batch.lengths == [len(p) for p in PROMPTS]
    assert batch.nbytes() == sum(batch.lengths) * tinygpt.kv_bytes_per_token(cfg)


def test_add_after_cache_grew_inside_step():
    # Кэш растёт внутри decode_step (inference mode); add снаружи должен работать.
    m = model()
    batch = tinygpt.KVBatch()
    first, kv = m.prefill(list(range(60)))
    batch.add(kv)
    out = [first]
    for _ in range(10):  # 60 → 70 позиций: тензор кэша вырос за GROW = 64
        out.append(int(m.decode_step(batch, torch.tensor([out[-1]]))[0]))
    second, kv2 = m.prefill([5, 6, 7])
    batch.add(kv2)
    nxt = m.decode_step(batch, torch.tensor([out[-1], second])).tolist()
    assert out + [nxt[0]] == tinygpt.generate_alone(m, list(range(60)), 12)
    assert [second, nxt[1]] == tinygpt.generate_alone(m, [5, 6, 7], 2)
