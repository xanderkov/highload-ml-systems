import json
import os
import select
import sys
import threading
import time

import forklib
import memlib

import unit_a

WORKERS = 4
ROUNDS = 20
SAMPLE_S = 0.2


def run_child(wfd: int, data, t0: float, other_fds) -> None:
    """Воркер: поток шлёт свой PSS в pipe, основной поток читает словарь."""
    for fd in other_fds:
        os.close(fd)
    done = threading.Event()

    def sample() -> None:
        with os.fdopen(os.dup(wfd), "w") as pipe:
            while True:
                pipe.write(f"{time.monotonic() - t0:.3f} {memlib.pss_mib():.2f}\n")
                pipe.flush()
                if done.wait(SAMPLE_S):
                    return

    sampler = threading.Thread(target=sample)
    sampler.start()
    unit_a.worker(data, ROUNDS)
    done.set()
    sampler.join()


def main() -> None:
    data = unit_a.build_data()
    base_rss = memlib.rss_mib()
    print(f"parent: {len(data)} keys, RSS {base_rss:.0f} MiB", file=sys.stderr)

    t0 = time.monotonic()
    pipes = {}  # fd чтения -> [индекс воркера, буфер]
    pids = []
    for i in range(WORKERS):
        r, w = os.pipe()
        pid = os.fork()
        if pid == 0:
            try:
                os.close(r)
                run_child(w, data, t0, list(pipes))
                os._exit(0)
            except BaseException:
                forklib.report_exception(f"worker {i + 1}")
                os._exit(1)
        os.close(w)
        pids.append(pid)
        pipes[r] = [i, b""]

    parent_points = []
    points = [[] for _ in range(WORKERS)]
    next_sample = 0.0
    while pipes:
        ready, _, _ = select.select(list(pipes), [], [], SAMPLE_S)
        now = time.monotonic() - t0
        if now >= next_sample:
            parent_points.append({"x": round(now, 3), "y": round(memlib.pss_mib(), 2)})
            next_sample = now + SAMPLE_S
        for fd in ready:
            chunk = os.read(fd, 65536)
            if not chunk:
                os.close(fd)
                del pipes[fd]
                continue
            i, buf = pipes[fd]
            *lines, buf = (buf + chunk).split(b"\n")
            pipes[fd][1] = buf
            for line in lines:
                x, y = line.split()
                points[i].append({"x": float(x), "y": float(y)})

    failed = False
    for i, pid in enumerate(pids):
        _, status = os.waitpid(pid, 0)
        if not (os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0):
            failed = True
            print(f"worker {i + 1} (pid {pid}) failed: {forklib.describe(status)}", file=sys.stderr)
    if failed:
        sys.exit(1)

    lines = [{"name": f"worker {i + 1}", "points": p} for i, p in enumerate(points)]
    lines.append({"name": "parent", "points": parent_points})
    print(json.dumps({"lines": lines}))


main()
