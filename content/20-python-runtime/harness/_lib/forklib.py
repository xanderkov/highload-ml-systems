"""Общие куски fork-харнессов: статус процесса, барьер на pipe, запуск в потомке."""

import os
import sys
import traceback


def describe(status: int) -> str:
    """Статус из waitpid человеческими словами."""
    if os.WIFEXITED(status):
        return f"exit code {os.WEXITSTATUS(status)}"
    return f"signal {os.WTERMSIG(status)}"


def wait_eof(fd: int) -> None:
    """Барьер: ждём, пока все пишущие концы pipe закроются."""
    while os.read(fd, 1):
        pass


def read_all(fd: int) -> bytes:
    """Читает pipe до EOF и закрывает его."""
    chunks = []
    while chunk := os.read(fd, 65536):
        chunks.append(chunk)
    os.close(fd)
    return b"".join(chunks)


def write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def report_exception(prefix: str) -> None:
    """Трассировка одной записью: несколько процессов не перемешают строки."""
    os.write(2, f"{prefix}: {traceback.format_exc()}".encode())


def run_in_child(fn, name: str) -> bytes:
    """Выполняет fn() в отдельном процессе и возвращает байты, которые она вернула.

    Память потомка уходит вместе с ним: следующий замер начинается с чистого
    процесса. Если потомок упал, печатает причину (трассировка уже в stderr)
    и завершает харнесс с кодом 1.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:
        try:
            os.close(r)
            write_all(w, fn())
            os._exit(0)
        except BaseException:
            report_exception(name)
            os._exit(1)
    os.close(w)
    data = read_all(r)
    _, status = os.waitpid(pid, 0)
    if not (os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0):
        print(f"{name} failed: {describe(status)}", file=sys.stderr)
        sys.exit(1)
    return data
