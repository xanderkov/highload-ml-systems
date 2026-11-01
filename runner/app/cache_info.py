"""Read cache sizes from the OS; runnable on the host without dependencies."""
import argparse
import json
import os
import platform
import re
import subprocess
from pathlib import Path


def _read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _size(text):
    match = re.fullmatch(r"(\d+)\s*([KMG]?)", text, re.I)
    return int(match[1]) * (1024 ** ("KMG".find(match[2].upper()) + 1) if match[2] else 1) if match else None


def linux_entries(root=Path("/sys/devices/system/cpu")):
    entries = {}
    allowed = os.sched_getaffinity(0) if hasattr(os, "sched_getaffinity") else None
    for cpu in sorted(root.glob("cpu[0-9]*")):
        if allowed is not None and int(cpu.name[3:]) not in allowed:
            continue
        for index in (cpu / "cache").glob("index*"):
            level, kind = _read(index / "level"), _read(index / "type")
            size = _size(_read(index / "size"))
            if level not in {"1", "2", "3"} or kind not in {"Data", "Unified"} or not size:
                continue
            key = (int(level), kind, size)
            entries[key] = {"level": int(level), "type": kind, "bytes": size, "group": "CPU"}
    return sorted(entries.values(), key=lambda row: (row["level"], row["bytes"]))


def _sysctl(key):
    proc = subprocess.run(["sysctl", "-n", key], capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def mac_entries(read=_sysctl):
    groups = []
    for index in range(16):
        prefix = f"hw.perflevel{index}"
        name = read(f"{prefix}.name")
        if name:
            groups.append((prefix, name))
    if not groups:
        groups = [("hw", "CPU")]
    entries = []
    for prefix, group in groups:
        for level, field in [(1, "l1dcachesize"), (2, "l2cachesize"), (3, "l3cachesize")]:
            raw = read(f"{prefix}.{field}")
            size = int(raw) if raw.isdigit() else 0
            if size:
                entries.append({"level": level, "type": "Data" if level == 1 else "Unified", "bytes": size, "group": group})
    return entries


def collect():
    system = platform.system()
    entries = mac_entries() if system == "Darwin" else linux_entries() if system == "Linux" else []
    model = _sysctl("machdep.cpu.brand_string") if system == "Darwin" else ""
    if system == "Linux":
        match = re.search(r"^model name\s*:\s*(.+)$", _read(Path("/proc/cpuinfo")), re.MULTILINE)
        model = match[1] if match else ""
    return {"architecture": platform.machine(), "model": model, "system": system, "source": "sysctl" if system == "Darwin" else "sysfs", "entries": entries}


def get_cache_info():
    native = collect()
    # Docker Desktop may expose cache levels but omit their sizes.
    if native["entries"] and native["model"]:
        return native
    host_file = Path(os.environ.get("HOST_CACHE_INFO", "/host-info/cache-info.json"))
    try:
        host = json.loads(host_file.read_text())
        aliases = {"arm64": "aarch64", "amd64": "x86_64"}
        arch = lambda value: aliases.get(str(value).lower(), str(value).lower())
        if arch(host.get("architecture")) == arch(native["architecture"]):
            valid = [e for e in host.get("entries", []) if isinstance(e, dict)
                     and e.get("level") in (1, 2, 3) and type(e.get("bytes")) is int
                     and e["bytes"] > 0 and isinstance(e.get("group"), str)]
            if valid or host.get("model"):
                return {**host, "entries": valid, "source": "host " + str(host.get("source", ""))}
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return native


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.dumps(collect(), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n")
    print(payload)
