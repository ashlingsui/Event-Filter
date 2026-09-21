#!/usr/bin/env python3
"""THE test the multi-user design rests on: a second user must not be able to read the first
user's outcomes or contacts. Not a unit test of application code — a test of the actual RLS
policies, run against real Postgres via real HTTP requests with real per-user JWTs. Querying with
the service role would prove nothing, since the service role bypasses RLS by definition; every
assertion here signs in as a real user first and queries through the anon key + that user's own
access_token, exactly as a browser would.

Creates two disposable users and one disposable event, runs the assertions, deletes everything it
created (best-effort, in a finally block) — safe to run repeatedly against a live project.

Usage:
    set -a; source supabase/.env; set +a
    python3 supabase/test_rls.py
"""
import secrets
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from supabase import rest

FAILURES = []
TOTAL = [0]


def check(label, condition, detail=""):
    TOTAL[0] += 1
    status = "PASS" if condition else "FAIL"
    print("  [{}] {}{}".format(status, label, " — {}".format(detail) if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


def _random_email():
    return "rls-test-{}@example.com".format(secrets.token_hex(6))


def main():
    svc = rest.service_client()
    password = "Rls-test-{}!".format(secrets.token_hex(8))

    print("Setup:")
    user_a = rest.admin_create_user(_random_email(), password)
    user_b = rest.admin_create_user(_random_email(), password)
    a_id, b_id = user_a["id"], user_b["id"]
    print("  created user A: {}".format(a_id))
    print("  created user B: {}".format(b_id))

    event = svc.insert("events", [{
        "source": "manual",
        "source_id": "rls-test-{}".format(secrets.token_hex(4)),
        "url": "https://example.com/rls-test",
        "name": "RLS test event",
        "start_at": "2026-01-01T00:00:00Z",
        "format": "unknown",
        "host_tier": "unknown",
    }])[0]
    event_id = event["id"]
    print("  created test event: {}".format(event_id))

    session_a = rest.sign_in(user_a["email"], password)
    session_b = rest.sign_in(user_b["email"], password)
    client_a = rest.user_client(session_a["access_token"])
    client_b = rest.user_client(session_b["access_token"])
    client_anon = rest.anon_client()

    try:
        print("\nUser A writes their own private rows:")
        outcome_a = client_a.insert("outcomes", [{
            "user_id": a_id, "event_id": event_id, "attended": True,
            "felt_score": 7, "felt_note": "user A's private note",
        }])
        check("A can insert their own outcome", bool(outcome_a))

        contact_a = client_a.insert("contacts", [{
            "user_id": a_id, "event_id": event_id, "name": "A's secret contact",
            "state": "met", "notes": "should never be visible to B",
        }])
        check("A can insert their own contact", bool(contact_a))

        profile_a = client_a.upsert("profiles", [{
            "id": a_id, "home_city": "Berkeley",
        }], on_conflict="id")
        check("A can write their own profile", bool(profile_a))

        intent_a = client_a.insert("intents", [{
            "user_id": a_id, "event_id": event_id, "intent": "want",
        }])
        check("A can insert their own intent", bool(intent_a))

        print("\nPositive control — A can read A's own rows back:")
        check("A sees their own outcome", len(client_a.select("outcomes", {"event_id": "eq.{}".format(event_id)})) == 1)
        check("A sees their own contact", len(client_a.select("contacts", {"event_id": "eq.{}".format(event_id)})) == 1)

        print("\nThe test that matters — B must see NONE of A's private rows:")
        b_sees_outcomes = client_b.select("outcomes", {"event_id": "eq.{}".format(event_id)})
        check("B cannot read A's outcome", len(b_sees_outcomes) == 0, "got {} row(s)".format(len(b_sees_outcomes)))

        b_sees_contacts = client_b.select("contacts", {"event_id": "eq.{}".format(event_id)})
        check("B cannot read A's contact", len(b_sees_contacts) == 0, "got {} row(s)".format(len(b_sees_contacts)))

        b_sees_profile = client_b.select("profiles", {"id": "eq.{}".format(a_id)})
        check("B cannot read A's profile", len(b_sees_profile) == 0, "got {} row(s)".format(len(b_sees_profile)))

        b_sees_intent = client_b.select("intents", {"event_id": "eq.{}".format(event_id), "user_id": "eq.{}".format(a_id)})
        check("B cannot read A's intent", len(b_sees_intent) == 0, "got {} row(s)".format(len(b_sees_intent)))

        print("\nWrite-side RLS — B's update/delete against A's row must affect zero rows:")
        patched = client_b.update(
            "outcomes",
            {"event_id": "eq.{}".format(event_id), "user_id": "eq.{}".format(a_id)},
            {"felt_score": 0},
        )
        check("B's UPDATE touches zero of A's rows", len(patched) == 0, "got {} row(s)".format(len(patched)))

        print("\nUnauthenticated (anon, no session at all) must also see nothing private:")
        check("anon cannot read outcomes", len(client_anon.select("outcomes", {"event_id": "eq.{}".format(event_id)})) == 0)
        check("anon cannot read contacts", len(client_anon.select("contacts", {"event_id": "eq.{}".format(event_id)})) == 0)

        print("\nPositive control — shared data IS visible to any signed-in user (RLS isn't just blocking everything):")
        events_seen_by_b = client_b.select("events", {"id": "eq.{}".format(event_id)})
        check("B can read the shared event catalog", len(events_seen_by_b) == 1)

    finally:
        print("\nCleanup:")
        try:
            svc.delete("outcomes", {"event_id": "eq.{}".format(event_id)})
            svc.delete("contacts", {"event_id": "eq.{}".format(event_id)})
            svc.delete("intents", {"event_id": "eq.{}".format(event_id)})
            svc.delete("profiles", {"id": "eq.{}".format(a_id)})
            svc.delete("events", {"id": "eq.{}".format(event_id)})
            rest.admin_delete_user(a_id)
            rest.admin_delete_user(b_id)
            print("  done")
        except requests.RequestException as exc:
            print("  cleanup had an error (may need manual removal): {}".format(exc))

    print("\n{} assertion(s), {} failed.".format(TOTAL[0], len(FAILURES)))
    if FAILURES:
        print("FAILED: {}".format(", ".join(FAILURES)))
        sys.exit(1)
    print("ALL PASSED — cross-user isolation holds.")


if __name__ == "__main__":
    main()
