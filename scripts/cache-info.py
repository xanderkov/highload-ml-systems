#!/usr/bin/env python3
"""Collect host cache sizes for Docker Desktop: python3 scripts/cache-info.py."""
import runpy
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
if len(sys.argv) == 1:
    sys.argv += ["--output", str(root / ".runtime/cache-info.json")]
runpy.run_path(str(root / "runner/app/cache_info.py"), run_name="__main__")
