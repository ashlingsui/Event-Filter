#!/usr/bin/env python3
"""Event Filter — step 1: ingest.

Pulls Luma + Haas CampusGroups + Partiful into one normalized row set per SPEC.md §2.
Does not filter, score, or enrich anything — bart_walk_min, reachable, participant,
target_proximity, format, cohort_saturation, prior_hook etc. stay null. That's step 2
(Enrich), not built yet. See BUILD_HANDOFF.md for the full build sequence.

Usage:
    python3 run_ingest.py
"""
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))

from ingest import campusgroups, luma, normalize, partiful

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config" / "calendars.json"
OUTPUT_PATH = ROOT / "data" / "events.json"


def load_config():
    with CONFIG_PATH.open() as f:
        return json.load(f)


def load_existing():
    if OUTPUT_PATH.exists():
        with OUTPUT_PATH.open() as f:
            return json.load(f)
    return []


def main():
    config = load_config()
    existing_rows = load_existing()
    session = requests.Session()

    print("Luma:")
    luma_rows = luma.fetch_all(config.get("luma_calendars", []), session=session)

    print("CampusGroups:")
    cg_endpoint = config.get("campusgroups", {}).get("endpoint", campusgroups.ENDPOINT)
    campus_rows = campusgroups.fetch_all(endpoint=cg_endpoint, session=session)

    print("Partiful:")
    partiful_rows = partiful.fetch_all(config.get("partiful_urls", []), session=session)
    partiful_rows += partiful.fetch_explore(session=session)

    rows = normalize.merge(existing_rows, luma_rows, campus_rows, partiful_rows)
    normalize.write(rows, OUTPUT_PATH)

    fresh_ids = {r["id"] for r in luma_rows + campus_rows + partiful_rows if r.get("id")}
    stale_retained = sum(1 for r in rows if r["id"] not in fresh_ids)

    summary = normalize.summarize(rows)
    print("\n{} events written to {}".format(summary["total"], OUTPUT_PATH))
    print("  by source: {}".format(summary["by_source"]))
    print("  missing start time: {}".format(summary["missing_start"]))
    print("  missing lat/lng: {}".format(summary["missing_geo"]))
    print("  retained from a previous run (no longer in any live feed): {}".format(stale_retained))


if __name__ == "__main__":
    main()
