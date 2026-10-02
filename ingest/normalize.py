"""Merge ingest sources into one row set. Dedup by id; nothing here touches enrichment fields —
that's step 2, and this step must not silently fill them in."""
import json
from pathlib import Path


def merge(existing_rows, *fresh_row_lists, guard=None):
    """existing_rows: whatever was already in events.json before this run (empty on first run).
    Retained for any id that no longer appears in a fresh pull — an event whose date has passed
    drops out of Luma's `period=future` feed, and a naive rebuild would silently delete that row
    along with its enrichment, its score, and any outcome capture keyed to it. That's exactly the
    calibration record the whole project exists to build, so: fresh data always wins for an id
    that's still live (a source may have updated guest_count, etc.), but an id that's gone quiet
    keeps its last known state rather than vanishing."""
    by_id = {}
    for row in existing_rows:
        if row.get("id"):
            by_id[row["id"]] = row
    for rows in fresh_row_lists:
        for row in rows:
            if row.get("id"):
                previous = by_id.get(row["id"])
                # Hand-set values (_manual.fields) survive the wholesale replacement — see
                # manual_guard.py. `guard` is None only for callers that don't track a run report.
                if guard is not None and previous is not None:
                    guard.carry_forward(previous, row)
                by_id[row["id"]] = row
    merged = list(by_id.values())
    merged.sort(key=lambda r: r.get("start") or "")
    return merged


def write(rows, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(rows, f, indent=2, default=str)
    return path


def summarize(rows):
    by_source = {}
    missing_start = 0
    missing_geo = 0
    for row in rows:
        by_source[row["source"]] = by_source.get(row["source"], 0) + 1
        if not row.get("start"):
            missing_start += 1
        if row.get("lat") is None or row.get("lng") is None:
            missing_geo += 1
    return {
        "total": len(rows),
        "by_source": by_source,
        "missing_start": missing_start,
        "missing_geo": missing_geo,
    }
