#!/usr/bin/env python3
"""Migrates data/outcomes.json into the `outcomes` table. Per the request: the three backfilled
rows (Grok Bot, Founder & Funder, Venture Math S02) get label_source='retrospective_backfill' and
predicted_p_locked = NULL — they have no real pre-event prediction, so there is nothing honest to
lock. Only the OpenRouter row gets a locked prediction, and it's the hand-reasoned 0.60 (SPEC's
own calibration record), not the tool's own predicted_p_tool=0.20 — predicted_p_locked exists to
freeze what the SYSTEM predicted before the fact for calibration purposes, and this codebase never
built an automated per-user prediction pipeline that ran before 2026-09-18, so the only "prediction
live at decision time" that means anything here is hers, hand-recorded, matching outcomes.json's
own predicted_p field.

Writes as the target user's own session (sign in, use their access_token) rather than the service
role — outcomes are owner-written data and the `own_outcomes` RLS policy already permits a user to
insert their own rows, so this exercises the real write path instead of bypassing it.

event_id here is a real Supabase events.id (uuid) — this script resolves each outcome row's event
by matching its `url` against events already pushed (push_events.py must run first, and the event
must still exist there; the OpenRouter row is a known gap, see below).

Usage:
    set -a; source supabase/.env; set +a
    python3 supabase/migrate_outcomes.py --email you@example.com --password '...'
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from supabase import rest

ROOT = Path(__file__).parent.parent
OUTCOMES_PATH = ROOT / "data" / "outcomes.json"

# Per the request: only this event carries a locked pre-event prediction.
LOCKED_PREDICTIONS = {
    "luma:openro-kcis": 0.60,
}


_VALID_HOST_TIERS = {"tier1_vc", "scaled_co", "startup", "student_club", "unknown"}
_VALID_FORMATS = {
    "build_night", "hackathon", "demo_day", "workshop", "panel", "fireside", "mixer",
    "lecture", "class", "unknown",
}


def _resolve_or_create_event(svc, row):
    """All four outcomes.json rows fail a straightforward events.json lookup: the three backfills
    predate the pipeline entirely, and the OpenRouter row itself has since rolled off Luma's
    period=future feed (see BUILD_HANDOFF.md — this is the same row that motivated the ingest
    retention fix, applied too late to save this specific one). Falls back to constructing a
    minimal `source='manual'` event from whatever fields the backfill itself already carries, so
    the FK is satisfiable without fabricating data that isn't there."""
    url = row.get("url")
    if url:
        matches = svc.select("events", {"url": "eq.{}".format(url), "select": "id"})
        if matches:
            return matches[0]["id"], "existing"

    size = row.get("size")
    manual_event = {
        "source": "manual",
        "source_id": row["event_id"],
        "url": url or "https://example.com/unknown/{}".format(row["event_id"]),
        "name": row.get("name") or "(untitled)",
        "start_at": row.get("date"),
        "venue": row.get("venue"),
        "city": row.get("city"),
        "host_names": row.get("host_names") or [],
        "host_tier": row.get("host_tier") if row.get("host_tier") in _VALID_HOST_TIERS else "unknown",
        "format": row.get("format") if row.get("format") in _VALID_FORMATS else "unknown",
        "size": size if isinstance(size, int) else None,
        "speakers": row.get("speakers") or [],
    }
    created = svc.upsert("events", [manual_event], on_conflict="source,source_id")
    return created[0]["id"], "created_manual"


def _outcome_row(row, user_id, event_uuid):
    label_source = "retrospective_backfill" if row.get("label_source") == "retrospective_backfill" else "prospective"
    predicted_p_locked = LOCKED_PREDICTIONS.get(row["event_id"])

    def as_bool_or_none(v):
        return v if isinstance(v, bool) else None

    details = {}
    for field in ("s1_detail", "s2_detail", "s3_detail", "s4_detail"):
        if row.get(field):
            details[field] = row[field]

    out = {
        "user_id": user_id,
        "event_id": event_uuid,
        "attended": bool(row.get("attended")),
        "partial": bool(row.get("partial")),
        "predicted_p_locked": predicted_p_locked,
        "felt_score": row.get("felt_score"),
        "felt_note": row.get("felt_note"),
        "s1_pov": as_bool_or_none(row.get("s1_pov")),
        "s2_contact": as_bool_or_none(row.get("s2_contact")),
        "s3_build": as_bool_or_none(row.get("s3_build")),
        "s4_cohort": as_bool_or_none(row.get("s4_cohort")),
        "details": details,
        "label_status": row.get("label_status") or "unknown",
        "label_source": label_source,
    }
    if predicted_p_locked is not None:
        out["locked_at"] = row.get("date")
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with OUTCOMES_PATH.open() as f:
        data = json.load(f)

    session = rest.sign_in(args.email, args.password)
    user_id = session["user"]["id"]
    client = rest.user_client(session["access_token"])
    svc = rest.service_client()  # read-only use here: resolving event uuids across the shared catalog

    rows_to_insert = []
    created_manual = []
    for row in data["rows"]:
        event_uuid, how = _resolve_or_create_event(svc, row)
        if how == "created_manual":
            created_manual.append(row["event_id"])
        rows_to_insert.append(_outcome_row(row, user_id, event_uuid))

    print("{} outcome rows, all resolved ({} matched an existing pushed event, {} created as source='manual')".format(
        len(rows_to_insert), len(rows_to_insert) - len(created_manual), len(created_manual)
    ))
    if created_manual:
        print("  created manual event rows for (predate the pipeline or have since rolled off the live feed):")
        for eid in created_manual:
            print("    - {}".format(eid))

    if args.dry_run or not rows_to_insert:
        for r in rows_to_insert:
            print(json.dumps(r, indent=2, default=str))
        return

    client.insert("outcomes", rows_to_insert, returning=False)
    print("inserted {} outcome rows for user {}".format(len(rows_to_insert), user_id))


if __name__ == "__main__":
    main()
