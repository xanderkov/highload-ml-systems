#!/bin/sh
# Run the inline-assembly comparison in the native Docker Compose runner.
set -eu
cd "$(dirname "$0")/.."
docker compose exec -T runner python - <<'PY'
import json
import platform
from pathlib import Path

from app.jobs import CONTENT_ROOT, run_job

source = (CONTENT_ROOT / "01-cpu-cache/snippets/matrix_sum_asm.c").read_text()
result = run_job({
    "mode": "benchmark",
    "lang": "c",
    "harness_dir": "01-cpu-cache/harness/matrix_sum",
    "units": {
        "a": "#define MATRIX_COLUMNS 1\n" + source,
        "b": "#define MATRIX_COLUMNS 0\n" + source,
    },
    "target": None,
})
if result["status"] != "ok" or not result.get("correct"):
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1)
print(f"Architecture: {platform.machine()}")
print("Both sums match.")
print(f"Rows:    {result['student_ms']:.3f} ms")
print(f"Columns: {result['baseline_ms']:.3f} ms")
print(f"Columns / rows: {result['speedup']:.2f}x")
print(f"Spread: {result['spread_pct']:.1f}%")
PY
