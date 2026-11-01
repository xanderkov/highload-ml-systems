"""Задание 1: сколько данных родителя копирует каждый воркер после fork.

Протокол одного замера юнита (в отдельном процессе-«хозяине», чтобы память
одного варианта не досталась следующему):

1. хозяин мерит свой RSS, строит данные (`build_data`), мерит RSS снова —
   разница и есть «данные родителя»; затем вызывает `prepare(data)`;
2. fork на WORKERS воркеров; барьер: все воркеры созданы;
3. каждый воркер и хозяин мерят свой PSS («сразу после fork»), барьер;
4. каждый воркер собирает ключи заново и вызывает `lookup` на каждом,
   мерит время прохода и PSS после, хозяин — свой PSS; барьер, и только
   потом воркеры выходят — иначе ранний выход одного менял бы доли PSS
   остальных.

pss_growth_ratio = (Σ PSS после − Σ PSS сразу после fork) / (WORKERS × данные
родителя), суммы по хозяину и воркерам: какую долю данных скопировал себе
каждый воркер. Полная копия у каждого воркера даёт ≈ 1.
"""

import json
import os
import select
import signal
import statistics
import sys
import time

import forklib
import memlib

import unit_a
import unit_b

WORKERS = 4
N_KEYS = 1_000_000
# Меньше этого прирост RSS — уже шум аллокатора, а не данные: доля от него
# ничего не значит.
MIN_DATA_MIB = 16.0
# Контрольная сумма — точное целое меньше 2**52: представимо в float без
# потерь, поэтому runner сравнивает его с tolerance 0.
CHECK_MOD = 1 << 52


def worker(index: int, unit, data, fds: dict) -> None:
    for fd in (fds["start_w"], fds["go_w"], fds["exit_w"], fds["res_r"]):
        os.close(fd)
    res = fds["res_w"]
    forklib.wait_eof(fds["start_r"])
    os.write(res, f"{index} start {memlib.pss_mib():.3f}\n".encode())
    forklib.wait_eof(fds["go_r"])
    acc = 0
    t0 = time.perf_counter()
    for i in range(N_KEYS):
        # Ключ — новая строка, собранная в воркере: в общих страницах
        # меняются только счётчики ссылок того, что хранит сама структура.
        token_id, score = unit.lookup(data, f"tok{i}")
        # Порядок ключей фиксирован, а сумма зависит от порядка и от обоих
        # полей: перепутанные score или сдвинутые id её меняют.
        acc = (acc * 1_000_003 + token_id * 100_003 + round(score * 100)) % CHECK_MOD
    ms = (time.perf_counter() - t0) * 1000
    os.write(res, f"{index} done {memlib.pss_mib():.3f} {ms:.3f} {acc}\n".encode())
    forklib.wait_eof(fds["exit_r"])


def host(unit) -> bytes:
    """Строит данные, форкает воркеров и возвращает итог одного замера (JSON)."""
    rss_before = memlib.rss_mib()
    data = unit.build_data()
    data_mib = memlib.rss_mib() - rss_before
    if data_mib < MIN_DATA_MIB:
        print(
            f"build_data() увеличил RSS родителя всего на {data_mib:.1f} МиБ "
            f"(нужно хотя бы {MIN_DATA_MIB:.0f}): долю скопированных данных "
            "не от чего считать. Данные должны строиться в build_data(), "
            "а не при импорте модуля.",
            file=sys.stderr,
        )
        sys.stderr.flush()
        os._exit(1)
    unit.prepare(data)

    fds = {}
    fds["start_r"], fds["start_w"] = os.pipe()
    fds["go_r"], fds["go_w"] = os.pipe()
    fds["exit_r"], fds["exit_w"] = os.pipe()
    fds["res_r"], fds["res_w"] = os.pipe()

    pids = []
    for index in range(WORKERS):
        pid = os.fork()
        if pid == 0:
            try:
                worker(index, unit, data, fds)
                os._exit(0)
            except BaseException:
                forklib.report_exception(f"worker {index + 1}")
                os._exit(1)
        pids.append(pid)
    for name in ("start_r", "go_r", "exit_r", "res_w"):
        os.close(fds[name])

    records = {"start": {}, "done": {}}
    buf = b""

    def collect(stage: str) -> None:
        nonlocal buf
        while len(records[stage]) < WORKERS:
            ready, _, _ = select.select([fds["res_r"]], [], [], 0.05)
            if ready:
                chunk = os.read(fds["res_r"], 65536)
                *lines, buf = (buf + chunk).split(b"\n")
                for line in lines:
                    index, kind, *values = line.decode().split()
                    records[kind][int(index)] = values
            for index, pid in enumerate(pids):
                # До последнего барьера ни один воркер не выходит сам:
                # любой выход здесь — сбой (исключение, сигнал, OOM).
                done, status = os.waitpid(pid, os.WNOHANG)
                if done:
                    print(f"worker {index + 1} (pid {pid}) failed: {forklib.describe(status)}", file=sys.stderr)
                    for other in pids:
                        if other != pid:
                            try:
                                os.kill(other, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                    sys.stderr.flush()
                    os._exit(1)

    os.close(fds["start_w"])
    collect("start")
    # Воркеры стоят на барьере go: хозяин мерит себя в том же состоянии.
    host_start = memlib.pss_mib()
    os.close(fds["go_w"])
    collect("done")
    host_done = memlib.pss_mib()
    os.close(fds["exit_w"])
    for index, pid in enumerate(pids):
        _, status = os.waitpid(pid, 0)
        if not (os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0):
            print(f"worker {index + 1} (pid {pid}) failed: {forklib.describe(status)}", file=sys.stderr)
            os._exit(1)

    pss_start = host_start + sum(float(records["start"][i][0]) for i in range(WORKERS))
    pss_done = host_done + sum(float(records["done"][i][0]) for i in range(WORKERS))
    checks = {records["done"][i][2] for i in range(WORKERS)}
    if len(checks) != 1:
        print(f"воркеры вернули разные контрольные суммы: {sorted(checks)}", file=sys.stderr)
        os._exit(1)
    return json.dumps({
        "ms": max(float(records["done"][i][1]) for i in range(WORKERS)),
        "check": int(checks.pop()),
        "data_mib": data_mib,
        "growth_mib": pss_done - pss_start,
        "ratio": (pss_done - pss_start) / (WORKERS * data_mib),
    }).encode()


def measure(name: str, unit) -> dict:
    """Один замер юнита в отдельном процессе-хозяине."""
    result = json.loads(forklib.run_in_child(lambda: host(unit), f"unit {name}: parent process"))
    print(
        f"unit {name}: data {result['data_mib']:.1f} MiB, "
        f"processes grew {result['growth_mib']:.1f} MiB, ratio {result['ratio']:.3f}, "
        f"pass {result['ms']:.0f} ms",
        file=sys.stderr,
    )
    return result


def main() -> None:
    units = {"a": unit_a, "b": unit_b}
    samples = []
    checks = {}
    ratios = {"a": [], "b": []}
    for trial in range(-int(os.environ["BENCH_WARMUP"]), int(os.environ["BENCH_REPEATS"])):
        sample = {}
        for offset in range(2):
            name = "ab"[(trial + offset) % 2]
            result = measure(name, units[name])
            sample[name] = result["ms"]
            checks[name] = float(result["check"])
            if trial >= 0:
                ratios[name].append(result["ratio"])
        if trial >= 0:
            samples.append(sample)
    metrics = {name: {"pss_growth_ratio": statistics.median(values)} for name, values in ratios.items()}
    print(json.dumps({"samples": samples, "check": checks, "metrics": metrics}))


main()
