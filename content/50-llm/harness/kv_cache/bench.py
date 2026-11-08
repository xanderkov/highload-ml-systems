"""Глава 1: генерация без KV-кэша и с ним; память кэша на запрос.

Код замера — в unit_a.py (snippets/kv_cache.py). Память — формула
tinygpt.kv_bytes_per_token: K и V каждого слоя на каждый токен, float32.
"""
import json
import os
import sys

import torch

import stand
import tinygpt
import unit_a


def main() -> None:
    _, service = stand.cpus()
    os.sched_setaffinity(0, service)
    torch.set_num_threads(len(service))
    model = tinygpt.make_model()
    per_token = tinygpt.kv_bytes_per_token(model.cfg)
    lines = {"без кэша, мс на токен": [], "с кэшем, мс на токен": [], "KV-кэш запроса, МиБ": []}
    for n in unit_a.LENGTHS:
        nocache = unit_a.ms_per_token(model, n, cached=False)
        cached = unit_a.ms_per_token(model, n, cached=True)
        mib = (len(unit_a.PROMPT) + n) * per_token / 2**20
        lines["без кэша, мс на токен"].append({"x": n, "y": round(nocache, 2)})
        lines["с кэшем, мс на токен"].append({"x": n, "y": round(cached, 2)})
        lines["KV-кэш запроса, МиБ"].append({"x": n, "y": round(mib, 2)})
        print(f"{n} токенов: без кэша {nocache:.2f} мс/токен, с кэшем {cached:.2f} мс/токен, "
              f"кэш {mib:.2f} МиБ", file=sys.stderr)
    print(f"KV на токен: {per_token} байт ({per_token // 1024} КиБ)", file=sys.stderr)
    print(json.dumps({"lines": [{"name": k, "points": v} for k, v in lines.items()]}, ensure_ascii=False))


if __name__ == "__main__":
    with stand.exclusive():
        main()
