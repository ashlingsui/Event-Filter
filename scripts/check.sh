#!/usr/bin/env bash
# Shared local verification for Event Filter. It intentionally performs no network or Supabase work.
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

python3 -B - <<'PY'
import ast
import json
from pathlib import Path

root = Path.cwd()
python_sources = [
    *root.glob("*.py"),
    *root.glob("capture/*.py"),
    *root.glob("enrich/*.py"),
    *root.glob("ingest/*.py"),
    *root.glob("score/*.py"),
    *root.glob("supabase/*.py"),
]
for path in sorted(python_sources):
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

for path in sorted((root / "config").glob("*.json")):
    json.loads(path.read_text(encoding="utf-8"))
for path in sorted((root / "data").glob("*.json")):
    json.loads(path.read_text(encoding="utf-8"))

print(f"syntax and JSON checks passed ({len(python_sources)} Python files)")
PY

python3 -B run_checks.py
