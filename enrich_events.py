#!/usr/bin/env python3
"""Event Filter — step 2: enrich.

Three tiers, run in this order (SPEC.md §3c):

1. Geocode -> bart_walk_min -> reachable. Deterministic, no judgment calls. Always runs.
2. Rule-based classification (enrich/rules.py) -> format, segments. Deterministic keyword/pattern
   matching over scraped text, no model, no network call, no API key. Always runs. "Tier 1" in
   SPEC.md §3c's three-tier scheme.
3. LLM pass (enrich/llm_enrich.py) -> participant, target_proximity, format, cohort_saturation,
   prior_hook (only fills what tier 1 left null). "Tier 3" — OPTIONAL, OFF BY DEFAULT. Needs
   ANTHROPIC_API_KEY, read from the real environment first, falling back to supabase/.env
   (gitignored) via supabase/config.py's existing dotenv loader. Never printed, echoed, or
   written anywhere.

("Tier 2" in SPEC.md §3c is a Claude chat session reading descriptions and writing judgments back
by hand — a human workflow, not something this script runs. llm_enrich.apply_manual() is the
existing path for applying that session's output.)

If ANTHROPIC_API_KEY is absent, tier 3 is skipped and this script exits non-zero after still
writing back whatever tiers 1-2 produced — never silently, which is what produced the exact
failure SPEC.md §3c documents: "the pipeline looked like it worked, and the damage surfaced days
later as 'the model rates nothing well.'" Tier 3 being optional does not mean its absence goes
unreported; it means the other two tiers already did real, visible work regardless of it.

Usage:
    python3 enrich_events.py
"""
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))

import supabase.config  # noqa: F401 — side effect only: loads supabase/.env into os.environ if present
from enrich import geocode, llm_enrich, rules

ROOT = Path(__file__).parent
EVENTS_PATH = ROOT / "data" / "events.json"


def main():
    with EVENTS_PATH.open() as f:
        rows = json.load(f)

    session = requests.Session()

    print("Geocode / reachable:")
    geocode.enrich_all(rows, session=session)

    print("Rule pass (tier 1, deterministic):")
    rules.enrich_all(rows, session=session)

    print("LLM pass (tier 3, optional):")
    rows, llm_ran, llm_eligible = llm_enrich.enrich_all(rows, session=session)

    with EVENTS_PATH.open("w") as f:
        json.dump(rows, f, indent=2, default=str)
    print("\n{} rows written back to {}".format(len(rows), EVENTS_PATH))

    if not llm_ran:
        still_null = sum(
            1 for r in rows
            if r.get("format") is None or r.get("participant") is None or r.get("target_proximity") is None
        )
        print(
            "\nTIER 3 SKIPPED: ANTHROPIC_API_KEY not set (checked the environment and "
            "supabase/.env) — optional and off by default (SPEC.md §3c). {} of {} rows were "
            "eligible for it; {} rows still have at least one null judgment field after tiers "
            "1-2. To fill more: run tier 1's rules improve over time, use a Claude session "
            "(SPEC.md §3c tier 2) + llm_enrich.apply_manual(), or set ANTHROPIC_API_KEY in "
            "supabase/.env for tier 3.".format(llm_eligible, len(rows), still_null),
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
