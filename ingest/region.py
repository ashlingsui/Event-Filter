"""Region filter applied at ingest — before enrichment ever sees a row. SPEC.md's pipeline is
staged ingest -> enrich -> score -> capture; filtering non-actionable noise this early saves every
later stage, especially the LLM enrichment pass (real API cost per row), from working on events
that were always going to be excluded from the board.

This is a MOVE, not a new filter: `app/build_data.py` already excluded out-of-state/international
rows at the very last pipeline step (`_in_california`, `CALIFORNIA_BOUNDS`,
`CALIFORNIA_CITY_PREFIXES`), which meant the full cost of enrich + score was still being paid on
every one of those rows before they were thrown away. The definition below is ported verbatim from
that function so there is exactly one place this geography logic lives; build_data.py now trusts
the `region_status` this stamps onto each row instead of recomputing membership itself, so the two
layers cannot silently disagree (see build_data.py's own verification pass).

Region, not reachability: this checks "is this event even in California" (available at ingest from
city/lat-lng/title, no enrichment needed), not "can she get there" (enrich/geocode.py's BART-walk
reachability, computed later and treated as a cost rather than a gate per SPEC.md's reachability
revision). A hard-to-reach California event still belongs in the feed; an event in Barcelona never
did.

Which calendars get filtered, and against which region, is config/calendars.json's job
(`region_filter` on a luma_calendars entry, or the top-level `partiful_region_filter`) — not
hardcoded here.
"""

# Moved from app/build_data.py's CALIFORNIA_BOUNDS, unchanged (checked live 2026-09-21: covers the
# whole state with margin, but nothing in a neighboring state).
REGION_BOUNDS = {
    "california": {"lat_min": 32.4, "lat_max": 42.1, "lng_min": -124.6, "lng_max": -114.0},
}

# Moved from app/build_data.py's CALIFORNIA_CITY_PREFIXES, unchanged.
REGION_CITIES = {
    "california": {
        "san francisco", "oakland", "berkeley", "emeryville", "palo alto", "san jose",
        "sacramento", "los angeles", "san diego", "mountain view", "menlo park",
        "fremont", "santa clara", "sunnyvale", "walnut creek", "san mateo", "redwood city",
    },
}

DEFAULT_REGION = "california"


def _title_prefix_city(name):
    """The source calendars use a "<City> | <title>" naming convention for anything outside
    California (confirmed live: "Barcelona | Claude...", "New York | Building with Claude...",
    "San Francisco | Claude Meetup..."). Moved verbatim from build_data.py's _in_california — a
    handful of rows have no lat/lng and no clean city field, so the title is the only signal left.
    Returns the lowercased prefix if the title looks like one, else None."""
    name = name or ""
    if "|" not in name:
        return None
    prefix = name.split("|", 1)[0].strip()
    if 0 < len(prefix.split()) <= 3 and prefix[:1].isupper():
        return prefix.lower()
    return None


def classify(row, region):
    """Returns 'in_region', 'out_of_region', or 'unknown'. Signal priority: lat/lng (most
    precise) -> the row's own city field -> the "<City> | title" convention -> unknown. An
    unrecognized `region` name also returns 'unknown' rather than raising, so a config typo flags
    rows for review instead of crashing the whole ingest run."""
    bounds = REGION_BOUNDS.get(region)
    cities = REGION_CITIES.get(region)
    if bounds is None or cities is None:
        return "unknown"

    lat, lng = row.get("lat"), row.get("lng")
    if lat is not None and lng is not None:
        inside = bounds["lat_min"] <= lat <= bounds["lat_max"] and bounds["lng_min"] <= lng <= bounds["lng_max"]
        return "in_region" if inside else "out_of_region"

    city = (row.get("city") or "").strip().lower()
    if city:
        return "in_region" if city in cities else "out_of_region"

    prefix = _title_prefix_city(row.get("name"))
    if prefix is not None:
        if prefix in cities:
            return "in_region"
        # A short, capitalized "<City> |" prefix that isn't a known city in this region is
        # confidently elsewhere (Barcelona, New York, Yamagata, Brisbane, Seoul all matched this
        # live) — used only to exclude, never to confirm a region beyond the known-cities set.
        return "out_of_region"

    return "unknown"


def apply_filter(rows, region_by_calendar_id, partiful_region=None, default_region=DEFAULT_REGION):
    """Classifies every row (so region_status is always a real, derived value — never fabricated)
    but only DROPS a row when its source/calendar is actually configured for filtering:
    - luma: region_by_calendar_id.get(row._raw.calendar_id)
    - partiful: partiful_region
    - campusgroups (always Berkeley) and any unconfigured luma calendar: never dropped.

    Unknown rows (no lat/lng, no recognized city, no parseable title prefix) are never dropped
    regardless of configuration — SPEC.md's missing-data policy: unknown is not false. They're
    counted as `flagged` for review.

    Runs on the full post-merge row set (not per-source fresh fetches) so a row ingest.normalize
    retained from a previous run — because it dropped out of this run's live feed — still gets
    re-classified and swept out if its calendar is configured for filtering. Filtering only the
    fresh fetch would let an already-ingested out-of-region row sit in data/events.json forever,
    since normalize.merge's stale-retention logic can't tell "deliberately filtered" from
    "genuinely expired."
    """
    kept, dropped, flagged = [], 0, 0
    for row in rows:
        source = row.get("source")
        if source == "luma":
            calendar_id = (row.get("_raw") or {}).get("calendar_id")
            enforce_region = region_by_calendar_id.get(calendar_id)
        elif source == "partiful":
            enforce_region = partiful_region
        else:
            enforce_region = None  # campusgroups — never configured, always Berkeley anyway

        status = classify(row, enforce_region or default_region)
        row["region_status"] = status

        if enforce_region and status == "out_of_region":
            dropped += 1
            continue
        if status == "unknown":
            flagged += 1
        kept.append(row)
    return kept, dropped, flagged
