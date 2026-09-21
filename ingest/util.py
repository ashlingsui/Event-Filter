"""Small helpers shared across ingest sources."""
from datetime import datetime


def duration_hr_from_iso(start_iso, end_iso):
    if not start_iso or not end_iso:
        return None
    try:
        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        return round((end - start).total_seconds() / 3600, 2)
    except ValueError:
        return None
