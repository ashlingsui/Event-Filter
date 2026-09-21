#!/usr/bin/env python3
"""Step 3.5: push locally-scored events into Supabase. Ingest/enrich/score stay local — the
browser can't fetch Luma or CampusGroups (CSP blocks cross-host fetch, SPEC.md §5) — so this is
the one new step: read data/events.json (already scored) and upsert into the shared `events`
catalog plus a per-user `event_scores` row, via the service role (bypasses RLS by design; this is
the pipeline writing shared + its own scoring history, not a user-facing write path).

Local field names were designed to mirror the SQL enums field-for-field (see schema.sql), so this
mapping is mostly mechanical — the one real translation is splitting the local composite id
("luma:evt-XXXX") back into (source, source_id) to match `events`' own unique constraint.

Usage:
    set -a; source supabase/.env; set +a
    python3 supabase/push_events.py --user-id <your-auth-uid>
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from supabase import rest

ROOT = Path(__file__).parent.parent
EVENTS_PATH = ROOT / "data" / "events.json"
MODEL_VERSION = "local-pipeline-v1"

_VALID_SOURCES = {"luma", "campusgroups", "partiful", "manual"}
_VALID_FORMATS = {
    "build_night", "hackathon", "demo_day", "workshop", "panel", "fireside", "mixer",
    "lecture", "class", "unknown",
}
_VALID_HOST_TIERS = {"tier1_vc", "scaled_co", "startup", "student_club", "unknown"}
_VALID_REASONS = {
    "not_reachable", "conflict", "quota_full", "spectator", "wrong_ladder",
    "recurring", "off_phase", "below_bar",
}


def _split_id(local_id):
    source, _, source_id = (local_id or "").partition(":")
    if source not in _VALID_SOURCES or not source_id:
        return None, None
    return source, source_id


def _event_row(row):
    source, source_id = _split_id(row.get("id"))
    if not source:
        return None
    raw = row.get("_raw") or {}
    description = raw.get("description_text")
    if not description and isinstance(raw.get("ld_json"), dict):
        description = raw["ld_json"].get("description")

    return {
        "source": source,
        "source_id": source_id,
        "url": row.get("url") or "",
        "name": row.get("name") or "(untitled)",
        "description": description,
        "start_at": row.get("start"),
        "end_at": row.get("end"),
        "duration_hr": row.get("duration_hr"),
        "venue": row.get("venue"),
        "city": row.get("city"),
        "lat": row.get("lat"),
        "lng": row.get("lng"),
        "host_names": row.get("host_names") or [],
        "host_tier": row.get("host_tier") if row.get("host_tier") in _VALID_HOST_TIERS else "unknown",
        "format": row.get("format") if row.get("format") in _VALID_FORMATS else "unknown",
        "size": row.get("size") if isinstance(row.get("size"), int) else None,
        "gated": bool(row.get("gated")),
        "recurring": bool(row.get("recurring")),
        "next_occurrence": row.get("next_occurrence"),
        "speakers": row.get("speakers") or [],
    }


def _score_row(row, event_uuid, user_id):
    reasons = [r for r in (row.get("reasons") or []) if r in _VALID_REASONS]
    primary = row.get("primary_reason")
    primary = primary if primary in _VALID_REASONS else None
    return {
        "user_id": user_id,
        "event_id": event_uuid,
        "model_version": MODEL_VERSION,
        "predicted_p": row.get("predicted_p"),
        "verdict": row.get("verdict"),
        "primary_reason": primary,
        "reasons": reasons,
        "participant": row.get("participant"),
        "target_proximity": row.get("target_proximity"),
        "cohort_saturation": row.get("cohort_saturation"),
        "prior_hook": row.get("prior_hook"),
        "companions": row.get("companions") or [],
        "trip_chained": bool(row.get("trip_chained")),
        "cost_blocks": row.get("cost_blocks"),
        "bart_walk_min": row.get("bart_walk_min"),
        "reachable": row.get("reachable"),
        "is_exploration": bool(row.get("is_exploration")),
        "why": (row.get("_raw") or {}).get("why"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True, help="auth.users id to attribute event_scores to")
    parser.add_argument("--dry-run", action="store_true", help="print what would be pushed, write nothing")
    args = parser.parse_args()

    with EVENTS_PATH.open() as f:
        local_rows = json.load(f)

    event_rows = []
    skipped = 0
    for row in local_rows:
        er = _event_row(row)
        if er is None:
            skipped += 1
            continue
        event_rows.append((row, er))

    print("{} local rows, {} mappable, {} skipped (unparseable id)".format(len(local_rows), len(event_rows), skipped))

    if args.dry_run:
        print(json.dumps(event_rows[0][1], indent=2, default=str) if event_rows else "(nothing to push)")
        return

    svc = rest.service_client()

    pushed_events = svc.upsert("events", [er for _, er in event_rows], on_conflict="source,source_id")
    by_key = {(e["source"], e["source_id"]): e["id"] for e in pushed_events}
    print("upserted {} events".format(len(pushed_events)))

    score_rows = []
    for row, er in event_rows:
        event_uuid = by_key.get((er["source"], er["source_id"]))
        if not event_uuid:
            continue
        score_rows.append(_score_row(row, event_uuid, args.user_id))

    svc.insert("event_scores", score_rows, returning=False)
    print("inserted {} event_scores rows for user {}".format(len(score_rows), args.user_id))


if __name__ == "__main__":
    main()
