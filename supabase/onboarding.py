#!/usr/bin/env python3
"""Onboarding backend — SPEC.md §5. The four questions plus the five-event ranking exercise. Pure
data layer: no UI here (that's the separate frontend effort), just the writes and the selection
logic a UI would call.

Four questions -> profiles columns, exactly per §5's table:
    Q1 "Where do you live, how do you get around?"       -> home_city/lat/lng, drives, has_ride_access
    Q2 "What are you optimizing for?"                     -> target_role, target_industry, target_companies, needs_sponsorship
    Q3 "What community are you already in?"               -> home_community
    Q4 "How many evenings a week?"                        -> weekly_slots
phase and free_weekdays are the "ask once in passing, not in the form" fields — no dedicated
question, a UI can set them via write_profile too whenever it learns them.

The ranking exercise ends onboarding on a verdict, not a save button (§5): show five real
upcoming events, ask "which would you go to?", and that IS the first intent data — the only
personal signal that exists before the new user has attended anything. Deliberately picked from
the shared events catalog alone (format/size/host_tier), not from event_scores, because a brand
new user has no scores yet — this is cold start, by construction.
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from supabase import rest


def write_profile(user_id, answers):
    """answers: any subset of the profiles columns (home_city, home_lat, home_lng, drives,
    has_ride_access, target_role, target_industry, target_companies, needs_sponsorship,
    home_community, weekly_slots, phase, free_weekdays). Upserts — safe to call incrementally as
    a multi-step onboarding form fills in."""
    svc = rest.service_client()
    row = dict(answers)
    row["id"] = user_id
    return svc.upsert("profiles", [row], on_conflict="id")[0]


def mark_onboarded(user_id):
    svc = rest.service_client()
    svc.update("profiles", {"id": "eq.{}".format(user_id)}, {"onboarded_at": "now()"}, returning=False)


def select_ranking_candidates(n=5):
    """Five real upcoming events, spread across format so the exercise actually discriminates
    preference rather than just re-confirming 'yes to everything' or 'no to everything'. Pulls
    from the shared catalog only — no per-user scoring exists yet for someone mid-onboarding."""
    svc = rest.service_client()
    upcoming = svc.select("events", {
        "start_at": "gt.now()",
        "order": "start_at.asc",
        "limit": "200",
        "select": "id,name,format,size,host_tier,start_at,city,url",
    })

    by_format = {}
    for e in upcoming:
        by_format.setdefault(e.get("format") or "unknown", []).append(e)

    picks = []
    formats = list(by_format.keys())
    random.shuffle(formats)
    for fmt in formats:
        if len(picks) >= n:
            break
        picks.append(by_format[fmt][0])

    # top up from whatever's left if fewer distinct formats than n exist
    if len(picks) < n:
        remaining = [e for e in upcoming if e not in picks]
        picks.extend(remaining[: n - len(picks)])

    return picks[:n]


def record_ranking_intents(user_id, picks):
    """picks: [{"event_id": uuid, "intent": "want"|"pass"}, ...] from the onboarding exercise.
    intent_anchored=False always here — not a stylistic choice, a structural fact: no verdict
    exists yet for a brand-new user, so there is nothing for the pick to be anchored BY. This is
    the cleanest "blind" intent data the system will ever get (SPEC.md §1b: 'capture the
    wildcard/exploration picks blind where practical')."""
    svc = rest.service_client()
    rows = [{
        "user_id": user_id,
        "event_id": p["event_id"],
        "intent": p["intent"],
        "intent_anchored": False,
    } for p in picks]
    return svc.upsert("intents", rows, on_conflict="user_id,event_id", returning=False)


if __name__ == "__main__":
    candidates = select_ranking_candidates()
    print("{} ranking-exercise candidates:".format(len(candidates)))
    for c in candidates:
        print("  - [{}] {} ({}, {})".format(c.get("format"), c.get("name"), c.get("city"), c.get("start_at")))
