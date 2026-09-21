"""Haas CampusGroups ingest. No auth. The feed returns the full Haas calendar regardless of
group_ids, so we pull everything and let step 2 (Enrich) route by clubId — see BUILD_HANDOFF.md.

Rows arrive as positional p0..pN keys; each row also carries a `fields` string naming what
those positions mean, so we zip by name instead of hardcoding indices (the API has changed
field order between rows in the wild)."""
import html
import re
from datetime import datetime, timedelta, timezone

import requests

from .schema import new_event

ENDPOINT = "https://haas.campusgroups.com/mobile_ws/v17/mobile_events_list"

_TAG_RE = re.compile(r"<[^>]+>")
_DATE_RE = re.compile(r"[A-Za-z]{3},?\s+[A-Za-z]{3}\s+\d{1,2},\s+\d{4}")
_TIME_RE = re.compile(r"\d{1,2}:\d{2}\s*[AP]M|\d{1,2}\s*[AP]M")


def _strip_html(text):
    return html.unescape(_TAG_RE.sub("", text or "")).strip()


def _normalize_time(token):
    return token if ":" in token else token.replace(" ", ":00 ")


def _parse_event_dates(raw_html):
    """Best-effort parse of the '<p>...</p><p>...</p>' date blob CampusGroups renders. Returns
    (start_dt, end_dt) as naive local datetimes, or (None, None) if the shape is unfamiliar —
    the raw HTML is kept in _raw for manual/step-2 recovery either way."""
    parts = [_strip_html(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", raw_html or "")]
    parts = [p for p in parts if p]
    if not parts:
        return None, None

    def to_dt(date_str, time_str):
        try:
            if time_str:
                return datetime.strptime("{} {}".format(date_str, time_str), "%a, %b %d, %Y %I:%M %p")
            return datetime.strptime(date_str, "%a, %b %d, %Y")
        except ValueError:
            return None

    if len(parts) == 1:
        date_match = _DATE_RE.search(parts[0])
        return (to_dt(date_match.group(0), None), None) if date_match else (None, None)

    first, second = parts[0], parts[1]
    date1 = _DATE_RE.search(first)
    date2 = _DATE_RE.search(second)

    if date1 and date2:
        # two-day event: "Fri, Sep 18, 2026 2:00 PM –" / "Sun, Sep 20, 2026 11:00 AM"
        time1 = _TIME_RE.search(first)
        time2 = _TIME_RE.search(second)
        start_dt = to_dt(date1.group(0), _normalize_time(time1.group(0)) if time1 else None)
        end_dt = to_dt(date2.group(0), _normalize_time(time2.group(0)) if time2 else None)
        return start_dt, end_dt

    if date1 and not date2:
        # same-day event: "Mon, Sep 21, 2026" / "7 PM – 9 PM"
        times = [_normalize_time(t) for t in _TIME_RE.findall(second)]
        start_dt = to_dt(date1.group(0), times[0]) if len(times) >= 1 else to_dt(date1.group(0), None)
        end_dt = to_dt(date1.group(0), times[1]) if len(times) >= 2 else None
        return start_dt, end_dt

    return None, None


def _to_utc_iso(dt, tz_offset_hours):
    if dt is None:
        return None
    utc_dt = dt.replace(tzinfo=timezone(timedelta(hours=tz_offset_hours))).astimezone(timezone.utc)
    return utc_dt.isoformat().replace("+00:00", "Z")


def _int_or_none(value):
    digits = re.sub(r"[^\d]", "", value or "")
    return int(digits) if digits else None


def _row_to_dict(item):
    field_names = [f for f in (item.get("fields") or "").split(",") if f]
    values = []
    i = 0
    while "p{}".format(i) in item:
        values.append(item.get("p{}".format(i)))
        i += 1
    return dict(zip(field_names, values))


def _from_campusgroups_row(parsed):
    row = new_event()
    event_id = parsed.get("eventId")
    row["id"] = "campusgroups:{}".format(event_id)
    row["source"] = "campusgroups"
    row["name"] = _strip_html(parsed.get("eventName")) or None
    row["venue"] = _strip_html(parsed.get("eventLocation")) or None
    row["city"] = "Berkeley"

    tz_offset = -7  # PDT default; overridden below if the feed says otherwise
    tz_match = re.search(r"GMT\s*([+-]\d+)", parsed.get("eventTimezone") or "")
    if tz_match:
        tz_offset = int(tz_match.group(1))

    start_dt, end_dt = _parse_event_dates(parsed.get("eventDates"))
    row["start"] = _to_utc_iso(start_dt, tz_offset)
    row["end"] = _to_utc_iso(end_dt, tz_offset)
    if start_dt and end_dt:
        row["duration_hr"] = round((end_dt - start_dt).total_seconds() / 3600, 2)

    row["size"] = _int_or_none(parsed.get("eventAttendees"))

    club_name = _strip_html(parsed.get("clubName"))
    if club_name:
        row["host_names"] = [club_name]

    event_url = parsed.get("eventUrl")
    row["url"] = (
        "https://haas.campusgroups.com{}".format(event_url)
        if event_url and event_url.startswith("/")
        else event_url
    )

    row["_raw"] = {
        "club_id": parsed.get("clubId"),
        "club_login": parsed.get("clubLogin"),
        "category": _strip_html(parsed.get("eventCategory")),
        "raw_date_html": parsed.get("eventDates"),
        "price_range": _strip_html(parsed.get("eventPriceRange")),
    }
    return row


def fetch_all(endpoint=ENDPOINT, limit=50, max_pages=6, session=None):
    session = session or requests.Session()
    rows = []
    seen_ids = set()
    for page in range(max_pages):
        resp = session.get(endpoint, params={"range": page * limit, "limit": limit}, timeout=20)
        resp.raise_for_status()
        items = resp.json()
        if not items:
            break
        page_had_event = False
        for item in items:
            parsed = _row_to_dict(item)
            event_id = parsed.get("eventId")
            if not event_id:
                continue
            page_had_event = True
            if event_id in seen_ids:
                continue
            seen_ids.add(event_id)
            rows.append(_from_campusgroups_row(parsed))
        if not page_had_event:
            break
    print("  campusgroups: {} events".format(len(rows)))
    return rows
