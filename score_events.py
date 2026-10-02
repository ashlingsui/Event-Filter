#!/usr/bin/env python3
"""Event Filter — step 3: score.

Two layers, deliberately separate:
  1. scorer.py — the value/cost MODEL. A weighted combination -> predicted_p, plus cost_blocks.
     See scorer.py for why it's shaped the way it is — the SPEC.md §1 allocation rule (campus
     serves S1/S4, trips must clear S2/S3) and the LESSONS.md #5 rule (value and cost never mix
     into one number) are both load-bearing there.
  2. verdicts.py — the decision POLICY layered on top: reachability-as-cost, the weekly slot
     quota, conflicts against real commitments, and machine-readable reason codes (verdict /
     primary_reason / reasons / unblock_action).

Usage:
    python3 score_events.py
"""
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import manual_guard
from score import scorer, verdicts

ROOT = Path(__file__).parent
EVENTS_PATH = ROOT / "data" / "events.json"
SUMMARY_PATH = ROOT / "data" / "score_summary.json"


def main():
    with EVENTS_PATH.open() as f:
        rows = json.load(f)

    guard = manual_guard.Report()

    print("Score:")
    with guard.protect(rows, "score:scorer"):
        scorer.score_all(rows)

    print("Verdicts:")
    with guard.protect(rows, "score:verdicts"):
        skip_summary, blocked_summary, suppressed_summary, unscored_summary = verdicts.resolve(rows)
    print("  skip_summary:       {}".format(skip_summary))
    print("  blocked_summary:    {}".format(blocked_summary))
    print("  suppressed_summary: {}".format(suppressed_summary))
    print("  unscored_summary:   {}".format(unscored_summary))

    verdict_counts = {}
    for r in rows:
        verdict_counts[r["verdict"]] = verdict_counts.get(r["verdict"], 0) + 1
    print("  verdicts: {}".format(verdict_counts))

    confidences = [r["confidence"] for r in rows if r.get("confidence") is not None]
    if confidences:
        print("  mean confidence: {:.2f} ({} rows)".format(sum(confidences) / len(confidences), len(confidences)))

    # events.json stays a bare array — ingest/enrich already depend on that shape. Aggregates go
    # in their own file so the frontend has them precomputed without recomputing or reshaping
    # the events file.
    with EVENTS_PATH.open("w") as f:
        json.dump(rows, f, indent=2, default=str)
    with SUMMARY_PATH.open("w") as f:
        json.dump({
            "scored_at": datetime.datetime.utcnow().isoformat() + "Z",
            "verdict_counts": verdict_counts,
            "skip_summary": skip_summary,
            "blocked_summary": blocked_summary,
            "suppressed_summary": suppressed_summary,
            "unscored_summary": unscored_summary,
            "manual_preservation": guard.as_dict(),
        }, f, indent=2)

    print("\n{} rows written back to {}".format(len(rows), EVENTS_PATH))
    print("summary written to {}".format(SUMMARY_PATH))
    guard.print_summary()

    top = sorted(
        (r for r in rows if r["verdict"] in ("go", "part", "go_if")),
        key=lambda r: r.get("predicted_p") or 0,
        reverse=True,
    )
    print("\nTop {} by predicted_p:".format(min(15, len(top))))
    for r in top[:15]:
        print("  [{:8s}] p={:.2f} cost={:<4} {}".format(
            r["verdict"], r.get("predicted_p") or 0, r.get("cost_blocks"), r.get("name")
        ))


if __name__ == "__main__":
    main()
