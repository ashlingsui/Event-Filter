"""Deterministic half of step 2 (Enrich): fill in missing lat/lng, then derive bart_walk_min and
reachable from real BART station coordinates. See BUILD_HANDOFF.md's build sequence — this runs
before the LLM pass so the (expensive, judgment-based) LLM classification never has to look at
an event that's already a hard-filter reject for being nowhere near BART.

Station list is a static snapshot (config/bart_stations.json) pulled from BART's own public API
— see the fetch used to generate it. Stations don't move; no need to hit that API every run.
"""
import json
import math
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
STATIONS_PATH = ROOT / "config" / "bart_stations.json"
CACHE_PATH = ROOT / "data" / "geocode_cache.json"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "EventFilter/1.0 (personal Bay Area event scoring tool)"}
NOMINATIM_RATE_LIMIT_SEC = 1.0  # usage policy: max 1 request/second

WALK_MPH = 3.0
# BUILD_HANDOFF.md: "Palo Alto, Menlo Park, Marina, Presidio are effectively unreachable." All of
# those sit well past a 25-minute walk from the nearest BART station; this threshold is chosen to
# match that judgment, not the other way around.
REACHABLE_WALK_MIN = 25

# CampusGroups routinely hides the exact room ("Private Location (sign in to display)"), but Haas
# club events are, as a matter of physical fact, on or immediately next to campus. Geocoding that
# placeholder string would fail or mislead; defaulting to Haas's own (verified) coordinates does
# not. Verified via Nominatim 2026-09-18, not from memory.
HAAS_LAT, HAAS_LNG = 37.8719277, -122.2537582

_UNGEOCODABLE_RE = re.compile(r"https?://|check event page|sign in to display", re.IGNORECASE)


def load_stations():
    with STATIONS_PATH.open() as f:
        return json.load(f)


def _load_cache():
    if CACHE_PATH.exists():
        with CACHE_PATH.open() as f:
            return json.load(f)
    return {}


def _save_cache(cache):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("w") as f:
        json.dump(cache, f, indent=2)


def haversine_miles(lat1, lng1, lat2, lng2):
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_station(lat, lng, stations):
    best = min(stations, key=lambda s: haversine_miles(lat, lng, s["lat"], s["lng"]))
    return best, haversine_miles(lat, lng, best["lat"], best["lng"])


def walk_minutes(miles):
    return round(miles / WALK_MPH * 60)


def _lookup_text(row):
    """What to geocode, or None if the venue text isn't a real address — a hidden-location
    placeholder or a bare URL geocodes to garbage, not just a miss, so those are excluded
    up front rather than sent to Nominatim."""
    # A structured street address (when the source gave us one, e.g. Partiful's address_lines)
    # geocodes far more reliably than a free-text venue name — a business name can be ambiguous,
    # non-English, or otherwise unmatched ("Yuja" failed; a Partiful event's venue name arrived as
    # Japanese text for a Ferry Building address and wrongly suppressed a real, very BART-adjacent
    # SF event). Prefer it when available.
    address_lines = (row.get("_raw") or {}).get("address_lines")
    if address_lines:
        return ", ".join(address_lines)

    venue = row.get("venue")
    if venue and not _UNGEOCODABLE_RE.search(venue):
        return "{}, {}".format(venue, row["city"]) if row.get("city") else venue
    return None


def _geocode_text(query, cache, session):
    if query in cache:
        return cache[query]
    resp = session.get(
        NOMINATIM_URL,
        params={"q": query, "format": "json", "limit": 1},
        headers=NOMINATIM_HEADERS,
        timeout=15,
    )
    time.sleep(NOMINATIM_RATE_LIMIT_SEC)
    result = None
    if resp.ok and resp.json():
        hit = resp.json()[0]
        result = {"lat": float(hit["lat"]), "lng": float(hit["lon"])}
    cache[query] = result
    return result


def enrich_row(row, stations, cache, session):
    """Mutates row in place. Fills lat/lng when derivable, then bart_walk_min and reachable.
    Leaves all three None — never a guess — when the location is genuinely unknown, per SPEC.md's
    missing-data policy: unknown and displayed, not silently rejected or silently assumed good."""
    if row.get("lat") is None or row.get("lng") is None:
        if row["source"] == "campusgroups":
            row["lat"], row["lng"] = HAAS_LAT, HAAS_LNG
            row["_raw"]["geo_source"] = "campus_default"
        else:
            query = _lookup_text(row)
            if query:
                hit = _geocode_text(query, cache, session)
                if hit:
                    row["lat"], row["lng"] = hit["lat"], hit["lng"]
                    row["_raw"]["geo_source"] = "nominatim:{}".format(query)

    if row.get("lat") is not None and row.get("lng") is not None:
        station, miles = nearest_station(row["lat"], row["lng"], stations)
        row["bart_walk_min"] = walk_minutes(miles)
        row["reachable"] = row["bart_walk_min"] <= REACHABLE_WALK_MIN
        row["_raw"]["nearest_bart"] = station["name"]
    else:
        row["bart_walk_min"] = None
        row["reachable"] = None


def enrich_all(rows, session=None):
    session = session or requests.Session()
    stations = load_stations()
    cache = _load_cache()
    geocode_calls = 0
    for row in rows:
        had_coords = row.get("lat") is not None
        enrich_row(row, stations, cache, session)
        if not had_coords and row.get("_raw", {}).get("geo_source", "").startswith("nominatim"):
            geocode_calls += 1
    _save_cache(cache)

    reachable_counts = {"reachable": 0, "unreachable": 0, "unknown": 0}
    for row in rows:
        if row["reachable"] is True:
            reachable_counts["reachable"] += 1
        elif row["reachable"] is False:
            reachable_counts["unreachable"] += 1
        else:
            reachable_counts["unknown"] += 1
    print("  geocode: {} live lookups (cache: {} entries)".format(geocode_calls, len(cache)))
    print("  reachable: {}".format(reachable_counts))
    return rows
