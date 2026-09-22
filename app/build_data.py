#!/usr/bin/env python3
"""Bundles data/*.json into app/generated/data.js so the static frontend can open with no
server (file://) and no fetch(). This script only reads from data/ and app/config/ and only
writes into app/generated/ — it never touches ingest/, enrich/, score/, or capture/, and it
never rewrites data/events.json. Re-run after every pipeline run: `python3 app/build_data.py`.

Everything this script derives (decision-line sentences, quota_full "lost its slot to" names,
duplicate-listing notes, map placement) is computed from real event fields already present in
data/events.json plus score/verdicts.py's own documented precedence and pass order — nothing
here re-scores or re-ranks an event. The one exception is `track` (professional | social_cohort),
which reads app/config/social_cohort_overrides.json, an explicit, human-curated, mostly-empty
allowlist — see that file's _note. Everything not in it stays on its real pipeline verdict.
"""
import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
APP_DIR = Path(__file__).parent
OUT_PATH = APP_DIR / "generated" / "data.js"
PRIVATE_OUT_PATH = APP_DIR / "generated" / "private_data.js"

# Tight to where the real event data actually lives (checked live 2026-09-21: 51 of 108 rows
# fall inside SF/Berkeley/Oakland/Emeryville plus a couple South Bay points; the rest are a
# global Claude Community calendar spanning Barcelona/Tokyo/Sydney/etc — genuinely elsewhere,
# not a geocoding error). A loose box just wastes canvas on empty ocean/Central Valley and
# shrinks the real cluster to a speck. Anything outside this box is "outside_bay_area", not
# silently reprojected into it.
BAY_AREA_BOUNDS = {"lat_min": 37.28, "lat_max": 37.96, "lng_min": -122.46, "lng_max": -121.98}

# California only (checked live 2026-09-21: covers the whole state with margin, but nothing in
# a neighboring state). Used to drop out-of-state/international rows from the board entirely,
# per Ashling's 2026-09-21 call: they're not "suppressed" (a solvable-friction category — a ride,
# a long drive) — they're categorically not happening, so they don't need to be counted either.
CALIFORNIA_BOUNDS = {"lat_min": 32.4, "lat_max": 42.1, "lng_min": -124.6, "lng_max": -114.0}

# The source calendars use a "<City> | <title>" naming convention for anything outside the Bay
# Area (confirmed live: "Barcelona | Claude...", "New York | Building with Claude...",
# "San Francisco | Claude Meetup..."). A handful of these rows have no lat/lng at all, so the
# only signal is the title prefix. Used ONLY to exclude — a title that doesn't match this pattern,
# or whose city isn't recognized either way, is left alone (unknown is not false: SPEC.md's
# missing-data policy applies to exclusion decisions too, not just displayed facts).
CALIFORNIA_CITY_PREFIXES = {
    "san francisco", "oakland", "berkeley", "emeryville", "palo alto", "san jose",
    "sacramento", "los angeles", "san diego", "mountain view", "menlo park",
    "fremont", "santa clara", "sunnyvale", "walnut creek", "san mateo", "redwood city",
}

# Real, published city coordinates — used only to orient the schematic fallback map (labels),
# never to place an event. Projected through the same _project() function as event markers so
# a label and a real nearby event marker land in a consistent relative position.
REFERENCE_CITIES = {
    "San Francisco": (37.7749, -122.4194),
    "Berkeley": (37.8715, -122.2730),
    "Oakland": (37.8044, -122.2712),
    "Emeryville": (37.8313, -122.2852),
    "Palo Alto": (37.4419, -122.1430),
}

REASON_SENTENCES = {
    "not_reachable": "Not BART-reachable, and didn't rank in this week's top 3 to justify the ride.",
    "conflict": "Overlaps a commitment you've already confirmed.",
    "spectator": "Spectator format — you'd be watching, not doing.",
    "wrong_ladder": "The room is VCs and founders, not people at your target companies.",
    "recurring": "Part of a recurring series; the next occurrence is already accounted for.",
    "off_phase": "Doesn't match your current build-phase focus.",
    "below_bar": "Didn't clear the bar on contact or build potential.",
}


def _parse_dt(iso):
    if not iso:
        return None
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _pacific(d):
    offset = -7 if 3 <= d.month <= 10 else -8
    return d + dt.timedelta(hours=offset)


def _week_key(local_date):
    y, w, _ = local_date.isocalendar()
    return f"{y}-W{w:02d}"


def _week_label(local_date):
    monday = local_date - dt.timedelta(days=local_date.weekday())
    sunday = monday + dt.timedelta(days=6)
    if monday.month == sunday.month:
        return f"{monday.strftime('%b %-d')}–{sunday.day}"
    return f"{monday.strftime('%b %-d')}–{sunday.strftime('%b %-d')}"


def _in_california(row):
    """True/False when confident, None when genuinely unknown (kept, never excluded — SPEC.md's
    missing-data policy: unknown is not false)."""
    lat, lng = row.get("lat"), row.get("lng")
    if lat is not None and lng is not None:
        b = CALIFORNIA_BOUNDS
        return b["lat_min"] <= lat <= b["lat_max"] and b["lng_min"] <= lng <= b["lng_max"]

    name = row.get("name") or ""
    if "|" in name:
        prefix = name.split("|", 1)[0].strip().lower()
        if prefix in CALIFORNIA_CITY_PREFIXES:
            return True
        # A short, capitalized "<City> |" prefix that isn't a known CA city is confidently
        # elsewhere (Barcelona, New York, Yamagata, Brisbane, Seoul all matched this live).
        if 0 < len(prefix.split()) <= 3 and name.split("|", 1)[0].strip()[:1].isupper():
            return False
    return None


def _map_bucket(row):
    lat, lng = row.get("lat"), row.get("lng")
    if lat is None or lng is None:
        return "unknown_location"
    b = BAY_AREA_BOUNDS
    if b["lat_min"] <= lat <= b["lat_max"] and b["lng_min"] <= lng <= b["lng_max"]:
        return "bay_area"
    return "outside_bay_area"


def _project(row, bucket):
    if bucket != "bay_area":
        return None
    b = BAY_AREA_BOUNDS
    x = (row["lng"] - b["lng_min"]) / (b["lng_max"] - b["lng_min"]) * 600
    y = (b["lat_max"] - row["lat"]) / (b["lat_max"] - b["lat_min"]) * 480
    return [round(x, 1), round(y, 1)]


def _address(row):
    venue = (row.get("venue") or "").strip()
    return venue if venue else "Address not published on listing"


def _host(row):
    names = [n for n in (row.get("host_names") or []) if n]
    return ", ".join(names) if names else "Host not listed"


def _social_line(row):
    """score/verdicts.py has no concept of a social/cohort lane — it scores every row, including
    these, as an ordinary professional candidate. The manual override (app/config/
    social_cohort_overrides.json) only changes which LANE the frontend puts the row in; it does
    not erase the real predicted_p the pipeline computed. Saying the event 'never receives a P'
    would be false — it received one, same as everything else — so this states the real number
    instead of hiding it, while still being clear it isn't the reason to go or skip."""
    p = row.get("predicted_p")
    p_txt = f"{p:.2f}" if isinstance(p, (int, float)) else "unscored"
    return (
        f"Social / cohort plan. The pipeline still scored it like any professional event "
        f"({p_txt} P, {row.get('primary_reason') or 'below_bar'}) before this override moved it "
        f"here — that number isn't why it's on your plan."
    )


def _decision_line(row, quota_winners_by_week, week_key):
    verdict = row.get("verdict")
    primary = row.get("primary_reason")
    p = row.get("predicted_p")
    p_txt = f"{p:.2f}" if isinstance(p, (int, float)) else "unscored"

    if verdict == "go":
        return f"Cleared the bar at {p_txt} P(contact ∪ build). Go with intent."
    if verdict == "go_if":
        return row.get("unblock_action") or "GO — if you can get a ride."
    if verdict == "part":
        if primary and primary in REASON_SENTENCES:
            return f"{p_txt} P(contact ∪ build), but {REASON_SENTENCES[primary][0].lower()}{REASON_SENTENCES[primary][1:]} Worth the part that's there, not the whole program."
        return f"{p_txt} P(contact ∪ build) — interesting, but the outcome isn't clear enough to spend the whole slot."
    if verdict == "skip":
        if primary == "quota_full":
            winners = quota_winners_by_week.get(week_key, [])
            others = [w for w in winners if w != row.get("name")]
            if others:
                return f"Cleared the bar at {p_txt}, but lost its slot to {', '.join(others)}."
            return f"Cleared the bar at {p_txt}, but lost its slot this week."
        if primary and primary in REASON_SENTENCES:
            return REASON_SENTENCES[primary]
        return "Not everything good belongs on your calendar."
    if verdict == "suppressed":
        return REASON_SENTENCES.get("not_reachable", "Suppressed as unreachable.")
    if verdict == "blocked":
        return "No parseable date — can't be ranked into a week yet."
    if verdict == "wildcard":
        return "Wildcard: scored low, going anyway — this is how the model finds out it's wrong."
    return "Unscored."


def build():
    events = json.loads((DATA_DIR / "events.json").read_text())
    score_summary = json.loads((DATA_DIR / "score_summary.json").read_text())
    outcomes = json.loads((DATA_DIR / "outcomes.json").read_text())
    pending_hypotheses = json.loads((DATA_DIR / "pending_hypotheses.json").read_text())
    overrides_doc = json.loads((APP_DIR / "config" / "social_cohort_overrides.json").read_text())
    social_ids = set(overrides_doc.get("social_cohort_event_ids", {}).keys())

    # Week grouping + quota_full winner names, computed once so decision lines can reference them.
    week_of = {}
    quota_winners_by_week = {}
    duplicate_of = {}
    seen_start_host = {}
    for row in events:
        d = _parse_dt(row.get("start"))
        if not d:
            continue
        local = _pacific(d)
        wk = _week_key(local)
        week_of[row["id"]] = wk
        if row.get("verdict") in ("go", "go_if"):
            quota_winners_by_week.setdefault(wk, []).append(row["name"])

        first_host = (row.get("host_names") or [None])[0]
        key = (row.get("start"), first_host)
        if first_host and key in seen_start_host and row.get("verdict") in ("go", "part", "skip"):
            duplicate_of[row["id"]] = seen_start_host[key]
        elif first_host:
            seen_start_host.setdefault(key, row["name"])

    out_events = []
    excluded_non_ca = []
    for row in events:
        if _in_california(row) is False:
            excluded_non_ca.append(row["name"])
            continue
        wk = week_of.get(row["id"])
        bucket = _map_bucket(row)
        track = "social_cohort" if row["id"] in social_ids else "professional"
        out_events.append({
            "id": row["id"],
            "name": row["name"],
            "source": row.get("source"),
            "url": row.get("url"),
            "start": row.get("start"),
            "end": row.get("end"),
            "week_key": wk,
            "venue": row.get("venue"),
            "address": _address(row),
            "city": row.get("city"),
            "lat": row.get("lat"),
            "lng": row.get("lng"),
            "map_bucket": bucket,
            "map_xy": _project(row, bucket),
            "bart_walk_min": row.get("bart_walk_min"),
            "reachable": row.get("reachable"),
            "host_display": _host(row),
            "host_tier": row.get("host_tier"),
            "format": row.get("format"),
            "size": row.get("size"),
            "track": track,
            "verdict": row.get("verdict"),
            "primary_reason": row.get("primary_reason"),
            "reasons": row.get("reasons") or [],
            "unblock_action": row.get("unblock_action"),
            "predicted_p": row.get("predicted_p"),
            "cost_blocks": row.get("cost_blocks"),
            "is_exploration": row.get("is_exploration"),
            "why_raw": (row.get("_raw") or {}).get("why"),
            "decision_line": (
                _decision_line(row, quota_winners_by_week, wk)
                if track == "professional"
                else _social_line(row)
            ),
            "duplicate_of_name": duplicate_of.get(row["id"]),
            "intent": row.get("intent"),
            "rsvp_state": row.get("rsvp_state"),
            "gated": row.get("gated"),
        })

    week_meta = {}
    for row in events:
        d = _parse_dt(row.get("start"))
        if not d:
            continue
        local = _pacific(d)
        wk = _week_key(local)
        if wk not in week_meta:
            week_meta[wk] = _week_label(local)

    # PRIVACY BOUNDARY (SPEC.md §4): data/outcomes.json and data/pending_hypotheses.json contain
    # named real people and judgments about them, which is exactly why .gitignore excludes those
    # two source files from the repo. They must never end up inside app/generated/data.js — that
    # file is committed (so the shipped static page works without a rebuild) and is meant to be
    # safe to hand to a recruiter or make public. Outcomes/hypotheses go in a SEPARATE generated
    # file that .gitignore excludes too, for Ashling's own local read-back/learning views only.
    reference_cities = []
    for name, (lat, lng) in REFERENCE_CITIES.items():
        xy = _project({"lat": lat, "lng": lng}, "bay_area")
        reference_cities.append({"name": name, "lat": lat, "lng": lng, "xy": xy})

    # score_summary.json's suppressed_summary.total (59) is the raw pipeline count and includes
    # every excluded non-California row — showing it as-is next to a board that no longer
    # displays those rows at all would overstate what's on screen. Recompute the total from the
    # already-CA-filtered out_events instead, so the "N suppressed" line matches what a click
    # into the drawer can actually show.
    ca_suppressed_total = sum(1 for e in out_events if e["verdict"] == "suppressed")

    public_payload = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "source_scored_at": score_summary.get("scored_at"),
        "events": out_events,
        "weeks": [{"key": k, "label": v} for k, v in sorted(week_meta.items())],
        "score_summary": score_summary,
        "ca_suppressed_total": ca_suppressed_total,
        "excluded_non_california_count": len(excluded_non_ca),
        "social_cohort_overrides_note": overrides_doc.get("_note"),
        "map_bounds": BAY_AREA_BOUNDS,
        "map_reference_cities": reference_cities,
    }
    private_payload = {
        "generated_at": public_payload["generated_at"],
        "outcomes": outcomes,
        "pending_hypotheses": pending_hypotheses,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("window.EVENT_FILTER_DATA = " + json.dumps(public_payload, indent=2) + ";\n")
    PRIVATE_OUT_PATH.write_text(
        "// PRIVATE — named real people. Never commit. See .gitignore and SPEC.md §4.\n"
        "window.EVENT_FILTER_PRIVATE_DATA = " + json.dumps(private_payload, indent=2) + ";\n"
    )
    print(f"wrote {OUT_PATH} ({len(out_events)} events, {len(week_meta)} weeks)")
    print(f"wrote {PRIVATE_OUT_PATH} (gitignored — outcomes + pending hypotheses)")
    print(f"excluded {len(excluded_non_ca)} non-California events entirely (not shown, not counted):")
    for name in excluded_non_ca:
        print(f"  - {name}")


if __name__ == "__main__":
    build()
