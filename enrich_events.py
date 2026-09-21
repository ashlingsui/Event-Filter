#!/usr/bin/env python3
"""Event Filter — step 2: enrich.

Two passes over data/events.json, in this order (deliberately):

1. Geocode → bart_walk_min → reachable. Deterministic, no judgment calls.
2. LLM pass → participant, target_proximity, format, cohort_saturation, prior_hook.
   Runs only on rows that survive pass 1 (reachable is True or still unknown) — no point
   spending judgment-based classification on an event that's already a hard-filter reject
   for being nowhere near BART. Matches the scoring order SPEC.md §3 locks in: hard filters
   first, weighted scoring second.

Needs ANTHROPIC_API_KEY in the environment for pass 2 to actually call the model; without it,
pass 2 is skipped and those fields stay null (visible, not silently guessed).

Usage:
    python3 enrich_events.py
"""
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))

from enrich import geocode, llm_enrich

ROOT = Path(__file__).parent
EVENTS_PATH = ROOT / "data" / "events.json"


def main():
    with EVENTS_PATH.open() as f:
        rows = json.load(f)

    session = requests.Session()

    print("Geocode / reachable:")
    geocode.enrich_all(rows, session=session)

    print("LLM pass:")
    llm_enrich.enrich_all(rows, session=session)

    with EVENTS_PATH.open("w") as f:
        json.dump(rows, f, indent=2, default=str)

    print("\n{} rows written back to {}".format(len(rows), EVENTS_PATH))


if __name__ == "__main__":
    main()
