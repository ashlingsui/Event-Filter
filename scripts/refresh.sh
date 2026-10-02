#!/usr/bin/env bash
# One command, whole pipeline: ingest -> enrich -> score -> app/build_data.py, then final counts.
# Any step failing stops the run and says so — a forgotten build_data.py used to leave a stale
# site behind with no error anywhere, so the build is a step here, not an afterthought.
#
# Needs network (ingest + enrich fetch live pages). Does NOT touch Supabase.
#
# Exit codes: 0 = refreshed (possibly with warnings printed above), non-zero = a step failed and
# app/generated/data.js was NOT rebuilt from this run.
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

current_step="starting"
on_error() {
  local code=$?
  echo >&2
  echo "################################################################" >&2
  echo "REFRESH FAILED during: ${current_step} (exit ${code})" >&2
  echo "The pipeline stopped here. app/generated/data.js was NOT rebuilt from this run, so the" >&2
  echo "site is still serving whatever it had before. Fix the step above and re-run." >&2
  echo "################################################################" >&2
}
trap on_error ERR

step() {
  current_step="$1"
  shift
  echo
  echo "=== ${current_step} ==="
  "$@"
}

warnings=()

step "1/4 ingest (run_ingest.py)" python3 run_ingest.py

# enrich_events.py exits 3 when optional tier 3 (LLM, needs ANTHROPIC_API_KEY) was skipped. That is
# not a failure — tiers 1-2 ran and wrote their results — but it is never silent either.
current_step="2/4 enrich (enrich_events.py)"
echo
echo "=== ${current_step} ==="
set +e
python3 enrich_events.py
enrich_code=$?
set -e
if [ "$enrich_code" -eq 3 ]; then
  warnings+=("enrich: tier 3 (LLM) was SKIPPED — no ANTHROPIC_API_KEY. Rows rely on tier 1 rules + hand entries; the rest stay 'unscored'.")
elif [ "$enrich_code" -ne 0 ]; then
  exit "$enrich_code"
fi

step "3/4 score (score_events.py)" python3 score_events.py
step "4/4 build site data (app/build_data.py)" python3 app/build_data.py

current_step="final counts"
echo
echo "=== final counts ==="
python3 -B - <<'PY'
import datetime as dt
import json
import sys
from pathlib import Path

root = Path.cwd()
events = json.loads((root / "data" / "events.json").read_text())
summary = json.loads((root / "data" / "score_summary.json").read_text())
text = (root / "app" / "generated" / "data.js").read_text()
site = json.loads(text[text.index("{"):text.rindex("}") + 1])

# The failure this exists to catch: build_data.py never ran (or ran against other data).
if len(site["events"]) != len(events):
    sys.exit("REFRESH FAILED: events.json has {} rows but app/generated/data.js has {} — the site "
             "build does not match the data.".format(len(events), len(site["events"])))
built = dt.datetime.fromisoformat(site["generated_at"].replace("Z", "+00:00"))
age = dt.datetime.now(dt.timezone.utc) - built
if age.total_seconds() > 600:
    sys.exit("REFRESH FAILED: app/generated/data.js was built {:.0f} minutes ago, not by this run.".format(age.total_seconds() / 60))

verdicts = summary["verdict_counts"]
mp = summary.get("manual_preservation", {})
conf = [e["confidence"] for e in events if e.get("confidence") is not None]
print("events:            {}".format(len(events)))
print("verdicts:          " + ", ".join("{} {}".format(k, v) for k, v in sorted(verdicts.items(), key=lambda kv: -kv[1])))
print("unscored:          {} of {} ({:.0f}%)".format(verdicts.get("unscored", 0), len(events), 100 * verdicts.get("unscored", 0) / max(1, len(events))))
print("mean confidence:   {:.2f}".format(sum(conf) / len(conf)) if conf else "mean confidence:   n/a")
print("hand-set rows:     {} (overwrites blocked this run: {})".format(mp.get("rows_with_manual_fields", 0), mp.get("overwrites_blocked", 0)))
print("out of region:     {} reached the site build (should be 0)".format(site.get("out_of_region_count")))
print("site data built:   {} UTC".format(site["generated_at"]))
print("scrape recorded:   {}".format(site.get("source_ingested_at") or "NOT RECORDED"))
PY

if [ "${#warnings[@]}" -gt 0 ]; then
  echo
  echo "WARNINGS:"
  for w in "${warnings[@]}"; do echo "  - ${w}"; done
fi
echo
echo "refresh complete."
