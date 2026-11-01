"""Измерение памяти процесса: PSS и RSS в МиБ."""


def _proc(pid):
    return f"/proc/{'self' if pid is None else int(pid)}"


def _kb_field(path, name):
    with open(path) as f:
        for line in f:
            if line.startswith(name + ":"):
                return int(line.split()[1]) / 1024.0
    raise RuntimeError(f"{name} not found in {path}")


def pss_mib(pid=None):
    """Pss из /proc/<pid|self>/smaps_rollup, МиБ."""
    return _kb_field(_proc(pid) + "/smaps_rollup", "Pss")


def rss_mib(pid=None):
    """VmRSS из /proc/<pid|self>/status, МиБ."""
    return _kb_field(_proc(pid) + "/status", "VmRSS")
