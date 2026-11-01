"""Эксперимент: данные torch-тензора после fork остаются общими.

Две группы по WORKERS воркеров, каждая в своём процессе-родителе:

- `dict`: тот же «токенайзер», что в крючке (`unit_a.build_dict`);
- `tensor`: float32-тензор того же размера в байтах, что и словарь в памяти
  родителя (`unit_a.build_tensor`).

Воркеры каждой группы за ROUNDS раундов читают все данные.

Каждый воркер шлёт свой PSS по ходу чтения. x — время от fork, с.
"""

import json
import os
import sys
import time
import traceback

import memlib

import unit_a

WORKERS = 2
ROUNDS = 10
PAUSE_S = 0.15


def worker(wfd: int, read, data, t0: float, exit_r: int) -> None:
    def report() -> None:
        os.write(wfd, f"{time.monotonic() - t0:.3f} {memlib.pss_mib():.2f}\n".encode())

    report()
    for r in range(ROUNDS):
        read(data, r / ROUNDS, (r + 1) / ROUNDS)
        report()
        time.sleep(PAUSE_S)
    # Барьер: выходим, только когда дочитали все. Ранний выход одного
    # воркера поднял бы PSS остальных: общих страниц делят меньше процессов.
    while os.read(exit_r, 1):
        pass


def describe(status: int) -> str:
    if os.WIFEXITED(status):
        return f"exit code {os.WEXITSTATUS(status)}"
    return f"signal {os.WTERMSIG(status)}"


def group(name: str, build, read, out: int) -> None:
    """Родитель группы: строит данные, форкает воркеров, пишет точки в out."""
    rss_before = memlib.rss_mib()
    data = build()
    data_mib = memlib.rss_mib() - rss_before
    os.write(out, f"data {data_mib:.2f}\n".encode())
    exit_r, exit_w = os.pipe()
    t0 = time.monotonic()
    pids = []
    readers = []
    for index in range(WORKERS):
        r, w = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                os.close(r)
                os.close(exit_w)
                for fd in readers:
                    os.close(fd)
                worker(w, read, data, t0, exit_r)
                os._exit(0)
            except BaseException:
                os.write(2, f"{name} worker {index + 1}: {traceback.format_exc()}".encode())
                os._exit(1)
        os.close(w)
        pids.append(pid)
        readers.append(r)
    os.close(exit_r)
    for index, r in enumerate(readers):
        # ROUNDS + 1 точек от каждого воркера; EOF раньше — воркер упал,
        # это покажет waitpid ниже.
        buf = b""
        while buf.count(b"\n") < ROUNDS + 1 and (chunk := os.read(r, 65536)):
            buf += chunk
        for line in buf.decode().splitlines():
            os.write(out, f"{index} {line}\n".encode())
    os.close(exit_w)
    for r in readers:
        os.close(r)
    for index, pid in enumerate(pids):
        _, status = os.waitpid(pid, 0)
        if not (os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0):
            print(f"{name} worker {index + 1} (pid {pid}) failed: {describe(status)}", file=sys.stderr)
            sys.stderr.flush()
            os._exit(1)


def run_group(name: str, build, read) -> tuple[float, list[dict]]:
    sys.stdout.flush()
    sys.stderr.flush()
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:
        try:
            os.close(r)
            group(name, build, read, w)
            os._exit(0)
        except BaseException:
            os.write(2, f"{name} parent: {traceback.format_exc()}".encode())
            os._exit(1)
    os.close(w)
    chunks = []
    while chunk := os.read(r, 65536):
        chunks.append(chunk)
    os.close(r)
    _, status = os.waitpid(pid, 0)
    if not (os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0):
        print(f"{name} parent failed: {describe(status)}", file=sys.stderr)
        sys.exit(1)
    data_mib = 0.0
    points = [[] for _ in range(WORKERS)]
    for line in b"".join(chunks).decode().splitlines():
        head, *rest = line.split()
        if head == "data":
            data_mib = float(rest[0])
        else:
            x, y = rest
            points[int(head)].append({"x": float(x), "y": float(y)})
    lines = [{"name": f"{name}: worker {i + 1}", "points": p} for i, p in enumerate(points)]
    return data_mib, lines


def main() -> None:
    dict_mib, dict_lines = run_group("dict", unit_a.build_dict, unit_a.read_dict)
    n_bytes = int(dict_mib * 2**20)
    tensor_mib, tensor_lines = run_group("tensor", lambda: unit_a.build_tensor(n_bytes), unit_a.read_tensor)
    print(f"dict {dict_mib:.0f} MiB, tensor {tensor_mib:.0f} MiB", file=sys.stderr)
    print(json.dumps({"lines": dict_lines + tensor_lines}))

main()
