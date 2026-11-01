import os
import resource
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

# RLIMIT_NPROC: защита от fork-бомбы. Ядро считает все задачи UID целиком:
# каждый поток — тоже задача, вместе с потоками самого runner'а, и
# одновременные задания делят этот бюджет на всех. Задание 2
# раздела python-runtime запускает до 4 × cores потоков torch (cores ≤ 32,
# см. threads_exercise/bench.py): при 64 стартовая конфигурация 4 процесса ×
# 16 потоков на 16-ядерной машине падала на создании потоков.
MAX_PROCESSES = 256
MAX_FILE_MB = 64
# Сколько дочитывать pipe после убийства группы, прежде чем бросить его.
DRAIN_TIMEOUT_S = 5


@dataclass
class ProcResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool


def _limits(memory_mb: int):
    def apply() -> None:
        memory = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_NPROC, (MAX_PROCESSES, MAX_PROCESSES))
        file_size = MAX_FILE_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (file_size, file_size))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return apply


def run(
    cmd: list[str],
    cwd: Path,
    timeout_s: float,
    memory_mb: int,
    env: dict[str, str] | None = None,
) -> ProcResult:
    # Своя сессия: процесс — лидер группы, и в конце задания убиваем всю группу,
    # чтобы форкнутые воркеры не пережили ни таймаут, ни падение родителя.
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        preexec_fn=_limits(memory_mb),
        env=env,
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        # Если сам процесс уже завершился, а таймаут вышел из-за потомка,
        # держащего pipe, это не таймаут задания: просто добираем вывод.
        timed_out = proc.poll() is None
        _kill_group(proc.pid)
        try:
            stdout, stderr = proc.communicate(timeout=DRAIN_TIMEOUT_S)
        except subprocess.TimeoutExpired as exc:
            # Pipe держит процесс, ушедший из группы (setsid): killpg его не
            # достаёт, и communicate() без таймаута ждал бы его вечно. Берём
            # собранное и закрываем pipe со своей стороны.
            stdout, stderr = _decode(exc.output), _decode(exc.stderr)
            for pipe in (proc.stdout, proc.stderr):
                if pipe is not None:
                    pipe.close()
            proc.wait()
    finally:
        _kill_group(proc.pid)
    return ProcResult(
        returncode=-1 if timed_out else proc.returncode,
        stdout=stdout or "",
        stderr=stderr or "",
        timed_out=timed_out,
    )


def _decode(data) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data


def _kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
