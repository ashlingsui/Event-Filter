#!/usr/bin/env bash
# Shared local verification for Event Filter. It intentionally performs no network or Supabase work.
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

python3 -B - <<'PY'
import ast
import json
import sys
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

# Privacy boundary (SPEC.md §4, app/build_data.py's event_private split): intent, rsvp_state,
# is_exploration, and companions reveal her actual plans — and companions can carry OTHER
# PEOPLE'S NAMES — so they must live only in the gitignored private_data.js, never in the
# committed, publicly-deployed data.js. This check exists because that boundary will get
# re-crossed by accident the next time someone adds a field to the event payload without
# thinking about where it's served from; a passing test is the only thing that catches it then.
data_js_path = root / "app" / "generated" / "data.js"
FORBIDDEN_PUBLIC_EVENT_FIELDS = {"intent", "rsvp_state", "is_exploration", "companions"}
if data_js_path.exists():
    text = data_js_path.read_text(encoding="utf-8")
    payload = json.loads(text[text.index("{"):text.rindex("}") + 1])
    leaked = [
        (event.get("id", "?"), sorted(FORBIDDEN_PUBLIC_EVENT_FIELDS & event.keys()))
        for event in payload.get("events", [])
        if FORBIDDEN_PUBLIC_EVENT_FIELDS & event.keys()
    ]
    if leaked:
        detail = "\n".join(f"  - {eid}: {fields}" for eid, fields in leaked)
        raise SystemExit(
            "PRIVACY BOUNDARY VIOLATION: app/generated/data.js (public, committed, served from a "
            f"public URL) contains field(s) that belong only in private_data.js:\n{detail}\n"
            "See app/build_data.py's event_private split and PLANS vs. METHOD comment."
        )
    print(f"privacy boundary check passed ({len(payload.get('events', []))} public events, no "
          f"{sorted(FORBIDDEN_PUBLIC_EVENT_FIELDS)} fields)")
else:
    print("privacy boundary check skipped (app/generated/data.js not found — run app/build_data.py)")

# Drift check: app/generated/data.js is a committed BUILD ARTIFACT of data/*.json + app/build_data.py.
# Regenerate it into a temp dir and fail if it differs from what is on disk — the stale-site
# failure (someone re-scored but never rebuilt, or hand-edited the artifact) otherwise passes
# silently. generated_at is the build clock, so it is excluded; everything else must match exactly.
import subprocess
import tempfile

needed = [root / "data" / name for name in ("events.json", "score_summary.json", "outcomes.json", "pending_hypotheses.json")]
if data_js_path.exists() and all(path.exists() for path in needed):
    with tempfile.TemporaryDirectory() as tmp:
        fresh_path = Path(tmp) / "data.js"
        result = subprocess.run(
            [sys.executable, "-B", str(root / "app" / "build_data.py"), "--out", str(fresh_path),
             "--private-out", str(Path(tmp) / "private_data.js")],
            capture_output=True, text=True, cwd=root,
        )
        if result.returncode != 0:
            raise SystemExit("DRIFT CHECK FAILED: app/build_data.py could not regenerate data.js:\n" + result.stderr[-2000:])

        def load(path):
            text = path.read_text(encoding="utf-8")
            payload = json.loads(text[text.index("{"):text.rindex("}") + 1])
            payload.pop("generated_at", None)
            return payload

        committed, fresh = load(data_js_path), load(fresh_path)
        if committed != fresh:
            differing = sorted(k for k in set(committed) | set(fresh) if committed.get(k) != fresh.get(k))
            changed_events = []
            if "events" in differing:
                old = {e["id"]: e for e in committed["events"]}
                new = {e["id"]: e for e in fresh["events"]}
                changed_events = sorted(i for i in set(old) | set(new) if old.get(i) != new.get(i))
            raise SystemExit(
                "DRIFT: app/generated/data.js does not match what app/build_data.py produces from the "
                f"current data/*.json. Differing top-level keys: {differing}; "
                f"{len(changed_events)} event(s) differ. Run `python3 app/build_data.py` (or "
                "scripts/refresh.sh) and commit the result."
            )
        print(f"drift check passed (data.js matches a fresh build; {len(fresh['events'])} events)")
else:
    print("drift check skipped (data.js or one of its input data/*.json files is missing)")
PY

python3 -B scripts/selftest.py

python3 -B run_checks.py
