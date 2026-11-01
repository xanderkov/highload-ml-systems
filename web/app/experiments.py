"""Compile editable C directly; resource limits are enforced by the runner."""
import re

WRAPPER = """
long long cache_probe(int *a, int phase) {
    if (phase == 0) {
        if (ARRAY_INTS > (1024ULL * 1024 * 1024) / sizeof(int)) return -1;
        return (long long)ARRAY_INTS * sizeof(int);
    }
    if (phase == 1) { prepare(a); return 0; }
    return measure(a);
}
"""


def prepare_units(starter, code):
    # Only a display label; the C compiler evaluates the actual expression.
    match = re.search(r"^\s*#\s*define\s+GAP_BYTES\s+([^\n]+)", code, re.MULTILINE)
    label = match[1].split("//", 1)[0].strip() if match else None
    return {"a": starter + WRAPPER, "b": code + WRAPPER}, label
