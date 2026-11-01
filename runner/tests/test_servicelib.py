import os
import sys
import time
from pathlib import Path

import pytest

_root = os.environ.get("CONTENT_ROOT", "/content")
sys.path.insert(0, os.path.join(_root, "30-naive-service", "harness", "_lib"))

from servicelib import (  # noqa: E402
    LoadGeneratorLagging,
    LoadResult,
    ServiceStartError,
    cpu_seconds,
    run_load,
    split_cpus,
    start_service,
)

APPS = Path(__file__).parent / "fixtures" / "apps"
LOAD, SERVICE = split_cpus()
OCTET = "application/octet-stream"


@pytest.fixture
def fast_app():
    return str(APPS / "svc_fast_app.py")


@pytest.fixture
def slow_app():
    return str(APPS / "svc_slow_app.py")


@pytest.fixture
def broken_app():
    return str(APPS / "svc_broken_app.py")


def _ppid(pid: int) -> int | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    return int(stat.rsplit(")", 1)[1].split()[1])


def service_pids(url: str) -> list[int]:
    """uvicorn с портом из url в cmdline плюс все его потомки."""
    port = url.rsplit(":", 1)[1]
    procs = [int(p) for p in os.listdir("/proc") if p.isdigit()]
    roots = set()
    for pid in procs:
        try:
            argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if b"uvicorn" in b" ".join(argv) and port.encode() in argv:
            roots.add(pid)
    found = set(roots)
    changed = True
    while changed:
        changed = False
        for pid in procs:
            if pid not in found and _ppid(pid) in found:
                found.add(pid)
                changed = True
    return sorted(found)


def pid_alive(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat.rsplit(")", 1)[1].split()[0] != "Z"


def test_split_cpus_gives_one_cpu_to_generator():
    assert len(LOAD) == 1 and len(SERVICE) >= 3 and not LOAD & SERVICE


def test_split_cpus_exits_on_small_machine(monkeypatch, capsys):
    monkeypatch.setattr(os, "sched_getaffinity", lambda pid: {0, 1, 2})
    with pytest.raises(SystemExit) as exc:
        split_cpus()
    assert exc.value.code == 3
    assert "на машине 3 логических CPU, задание требует ≥ 4 логических CPU" in capsys.readouterr().err


def test_goodput_and_percentiles():
    r = LoadResult(latencies_ms=[10, 20, 30, 1000], errors=1, lag_ms_p99=0, responses=[b""] * 4 + [None], duration_s=1)
    assert r.goodput(slo_ms=100) == 3 and r.p50() == 25
    assert r.throughput() == 4


def test_fast_service_answers_every_request(fast_app):
    with start_service(fast_app, cpus=SERVICE) as url:
        result = run_load(url, rps=200, duration_s=0.5, make_body=lambda i: b"x", content_type=OCTET, cpus=LOAD)
    assert result.errors == 0
    assert len(result.latencies_ms) == 100
    assert result.responses == [b"ok"] * 100
    assert result.p99() < 1000


def test_open_loop_counts_latency_from_schedule(slow_app):
    with start_service(slow_app, cpus=SERVICE) as url:
        result = run_load(url, rps=20, duration_s=1, make_body=lambda i: b"x", content_type=OCTET, cpus=LOAD)
    assert result.errors == 0
    assert result.p99() > 2000  # очередь растёт: закрытый цикл показал бы ~200 мс


def test_timeouts_are_counted_as_errors(slow_app):
    with start_service(slow_app, cpus=SERVICE) as url:
        result = run_load(url, rps=20, duration_s=0.5, make_body=lambda i: b"x", content_type=OCTET,
                          cpus=LOAD, timeout_s=0.5)
    assert result.errors > 0
    assert result.responses.count(None) == result.errors


def test_broken_app_raises_with_stderr(broken_app):
    with pytest.raises(ServiceStartError, match="SyntaxError"):
        with start_service(broken_app, cpus=SERVICE):
            pass


def test_service_is_pinned_to_its_cpus(fast_app):
    with start_service(fast_app, workers=2, cpus=SERVICE) as url:
        pids = service_pids(url)
        assert len(pids) >= 3  # мастер + 2 воркера
        assert all(os.sched_getaffinity(p) == SERVICE for p in pids)


def test_no_service_processes_left(fast_app):
    with start_service(fast_app, workers=2, cpus=SERVICE) as url:
        pids = service_pids(url)
    assert pids
    time.sleep(0.5)
    assert all(not pid_alive(p) for p in pids)


def test_cpu_seconds_of_busy_process():
    start = cpu_seconds([os.getpid()])
    deadline = time.process_time() + 0.3
    while time.process_time() < deadline:
        pass
    assert cpu_seconds([os.getpid()]) - start >= 0.2


def test_lagging_generator_is_reported(fast_app):
    def slow_body(i):  # 2 мс на тело при 1000 RPS: генератор заведомо не успевает
        time.sleep(0.002)
        return b"x"

    with start_service(fast_app, cpus=SERVICE) as url, pytest.raises(LoadGeneratorLagging):
        run_load(url, rps=1000, duration_s=0.5, make_body=slow_body, content_type=OCTET, cpus=LOAD)


def test_health_check_ignores_proxy_env(fast_app, monkeypatch):
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    with start_service(fast_app, cpus=SERVICE) as url:
        assert url.startswith("http://127.0.0.1:")
