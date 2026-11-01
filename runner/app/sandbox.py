import resource
import subprocess
from dataclasses import dataclass
from pathlib import Path

MAX_PROCESSES = 64
MAX_FILE_MB = 64


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
    try:
        completed = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            preexec_fn=_limits(memory_mb),
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return ProcResult(
            returncode=-1,
            stdout=exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
            stderr=exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or ""),
            timed_out=True,
        )
    return ProcResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        timed_out=False,
    )
