import functools
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.sandbox import run as sandboxed_run

CC = "gcc"
COMPILE_TIMEOUT_S = 10
# gcc compiling a few dozen lines of student C never needs anywhere near this;
# it exists to bound a pathological allocation (recursive macro, huge static
# initializer) so the compiler OOMs itself instead of taking the runner
# process down with it.
COMPILE_MEMORY_MB = 1024

# Explicit minimal environment for both compiling and running student-derived
# processes — sandbox.run(env=None) would otherwise inherit the whole runner
# service's environment. LC_ALL/LANG=C also pins printf's decimal separator
# (bench.c prints timings with "%f", which is locale-sensitive).
MINIMAL_ENV = {
    "PATH": "/usr/bin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
    "HOME": "/tmp",
}


class CompileError(Exception):
    """Compilation failed. `unit` is the job's unit key ("a"/"b") for a
    per-unit compile failure, or None for a harness/link-stage failure —
    callers must not surface `line` to the student unless `unit == "b"`,
    since a matched line always refers to whichever file was actually being
    compiled, which may not be the student's own submission."""

    def __init__(self, log: str, line: int | None, unit: str | None = None) -> None:
        super().__init__(log)
        self.log = log
        self.line = line
        self.unit = unit


class CompileTimeout(Exception):
    def __init__(self, log: str) -> None:
        super().__init__(log)
        self.log = log


@dataclass
class BuildResult:
    binary: Path
    compile_command: str


@functools.cache
def native_flag(cc: str = CC) -> str:
    """Подбирает флаг нативной оптимизации: он разный на x86 и aarch64."""
    for flag in ("-march=native", "-mcpu=native"):
        probe = subprocess.run(
            [cc, flag, "-x", "c", "-c", "-", "-o", "/dev/null"],
            input="int main(void){return 0;}",
            text=True,
            capture_output=True,
            check=False,
        )
        if probe.returncode == 0:
            return flag
    return ""


def _defines(defines: dict) -> list[str]:
    return [f"-D{key}={value}" for key, value in defines.items()]


def build_c(
    work: Path,
    harness_dir: str | Path,
    units: dict[str, str],
    cflags: list[str],
    defines: dict,
    unit_cflags: dict[str, list[str]] | None = None,
) -> BuildResult:
    # Resolve to an absolute path up front: _run_compiler now runs the
    # compiler through sandbox.run with cwd=work, so a relative harness_dir
    # (resolved against the caller's cwd, not the compiler's) must be turned
    # into an absolute path before it goes into any compiler command.
    harness = Path(harness_dir).resolve()
    meta_function = _function_name(harness)
    flags = [*cflags, native_flag(), *_defines(defines)]
    flags = [flag for flag in flags if flag]

    objects = []
    for name, source in units.items():
        source_path = work / f"unit_{name}.c"
        source_path.write_text(source, encoding="utf-8")
        object_path = work / f"unit_{name}.o"
        command = [CC, *flags, *(unit_cflags or {}).get(name, []), f"-D{meta_function}=fn_{name}", "-c", str(source_path), "-o", str(object_path)]
        _run_compiler(command, work, source_path=source_path, unit=name)
        objects.append(str(object_path))

    binary = work / "bench"
    command = [CC, *flags, str(harness / "bench.c"), *objects, "-o", str(binary), "-lm"]
    # source_path=None: a link/harness-stage failure is never the student's
    # own file, so no line number is ever attributed to it (see CompileError).
    _run_compiler(command, work, source_path=None, unit=None)
    return BuildResult(binary=binary, compile_command=" ".join(command))


def _function_name(harness: Path) -> str:
    import yaml

    meta = yaml.safe_load((harness / "meta.yml").read_text(encoding="utf-8"))
    return meta["function"]


def _run_compiler(command: list[str], cwd: Path, source_path: Path | None, unit: str | None) -> None:
    # Routed through the same sandbox as student binaries: gcc compiling
    # untrusted student source is itself untrusted input (unbounded macro
    # expansion / static initializers can make it allocate without limit),
    # so it gets the same memory cap, process cap, and minimal environment.
    result = sandboxed_run(command, cwd, timeout_s=COMPILE_TIMEOUT_S, memory_mb=COMPILE_MEMORY_MB, env=MINIMAL_ENV)
    if result.timed_out:
        raise CompileTimeout(result.stderr or result.stdout or "компиляция превысила лимит времени")
    if result.returncode != 0:
        line = None
        if source_path is not None:
            # Only trust a line number that gcc attributes to exactly the
            # file we asked it to compile — not the harness, not a header
            # pulled in by #include, not a macro-expansion site elsewhere.
            pattern = re.compile(rf"^{re.escape(str(source_path))}:(\d+):\d+:\s*error", re.MULTILINE)
            match = pattern.search(result.stderr)
            if match:
                line = int(match.group(1))
        raise CompileError(result.stderr, line, unit=unit)
