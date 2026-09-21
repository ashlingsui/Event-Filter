"""Luma ingest. Richer JSON endpoint first (undocumented, may break); ICS is the documented
fallback if it does. Both verified live 2026-09-17/18 — see BUILD_HANDOFF.md."""
import html
import re
from datetime import datetime, timezone

import requests

from .schema import new_event
from .util import duration_hr_from_iso as _duration_hr

JSON_ENDPOINT = "https://api.lu.ma/calendar/get-items"
ICS_ENDPOINT = "https://api.lu.ma/ics/get"


def _from_json_entry(entry, calendar_id, calendar_name, calendar_tier):
    event = entry.get("event") or {}
    row = new_event()
    # Externally-hosted events cross-posted onto a Luma calendar (platform: "external", e.g. a
    # Partiful link submitted to an OpenRouter calendar) carry no event.api_id and their event.url
    # is already the full external URL, not a lu.ma slug — the normal shape assumes both.
    event_id = event.get("api_id") or entry.get("api_id")
    row["id"] = "luma:{}".format(event_id) if event_id else None
    row["source"] = "luma"
    slug = event.get("url")
    if not slug:
        row["url"] = None
    elif slug.startswith("http"):
        row["url"] = slug
    else:
        row["url"] = "https://lu.ma/{}".format(slug)
    row["name"] = event.get("name")
    row["start"] = event.get("start_at")
    row["end"] = event.get("end_at")
    row["duration_hr"] = _duration_hr(row["start"], row["end"])

    geo = event.get("geo_address_info") or {}
    row["city"] = geo.get("city")
    coord = event.get("coordinate") or {}
    row["lat"] = coord.get("latitude")
    row["lng"] = coord.get("longitude")

    seen = set()
    host_names = []
    for h in entry.get("hosts") or []:
        name = h.get("name")
        if name and name not in seen:
            seen.add(name)
            host_names.append(name)
    row["host_names"] = host_names
    row["size"] = entry.get("guest_count")

    # require_approval deliberately excluded: it's Luma's near-universal RSVP default (true even
    # on a 500+-spot event), not a scarcity signal. Actual capacity pressure is what BUILD_HANDOFF
    # means by "gated events are disproportionately the small high-value ones."
    ticket_info = entry.get("ticket_info") or {}
    row["gated"] = bool(ticket_info.get("is_near_capacity") or ticket_info.get("is_sold_out"))

    row["_raw"] = {
        "calendar_id": calendar_id,
        "calendar_name": calendar_name,
        "calendar_tier": calendar_tier,
        "sublocality": geo.get("sublocality"),
        "location_type": event.get("location_type"),
        "ticket_info": entry.get("ticket_info"),
    }
    return row


def fetch_via_json(calendar_id, calendar_name, calendar_tier, session, pagination_limit=50):
    resp = session.get(
        JSON_ENDPOINT,
        params={"calendar_api_id": calendar_id, "period": "future", "pagination_limit": pagination_limit},
        timeout=20,
    )
    resp.raise_for_status()
    entries = resp.json().get("entries", [])
    return [_from_json_entry(e, calendar_id, calendar_name, calendar_tier) for e in entries]


_ICS_HOST_RE = re.compile(r"Hosted by ([^\\]+?)(?:\\n|$)")
# ICS escapes newlines as a literal backslash+n, not real whitespace, so \S+ would swallow
# straight through them into the rest of the description — exclude backslash explicitly.
_ICS_URL_RE = re.compile(r"(https://luma\.com/[^\s\\]+)")


def _unfold_ics(text):
    """RFC5545 line folding: a continuation line starts with a space or tab."""
    lines = text.replace("\r\n", "\n").split("\n")
    out = []
    for line in lines:
        if line.startswith((" ", "\t")) and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _parse_ics_dt(value):
    try:
        dt = datetime.strptime(value.strip(), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def _from_ics_vevent(block, calendar_id, calendar_name, calendar_tier):
    fields = {}
    for line in block:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.split(";")[0]
        fields.setdefault(key, value)

    row = new_event()
    uid = fields.get("UID", "").split("@")[0]
    row["id"] = "luma:{}".format(uid) if uid else None
    row["source"] = "luma"
    row["name"] = html.unescape(fields.get("SUMMARY", "")) or None

    description = fields.get("DESCRIPTION", "")
    url_match = _ICS_URL_RE.search(description)
    location = fields.get("LOCATION", "")
    if url_match:
        row["url"] = url_match.group(1)
    elif location.startswith("http"):
        row["url"] = location

    host_match = _ICS_HOST_RE.search(description)
    if host_match:
        names = re.split(r"\s*&\s*", host_match.group(1).strip())
        row["host_names"] = [n for n in names if n and "other" not in n.lower()]

    row["start"] = _parse_ics_dt(fields["DTSTART"]) if "DTSTART" in fields else None
    row["end"] = _parse_ics_dt(fields["DTEND"]) if "DTEND" in fields else None
    row["duration_hr"] = _duration_hr(row["start"], row["end"])

    if location and not location.startswith("http"):
        row["venue"] = location

    geo = fields.get("GEO")
    if geo and ";" in geo:
        lat_str, lng_str = geo.split(";", 1)
        try:
            row["lat"] = float(lat_str)
            row["lng"] = float(lng_str)
        except ValueError:
            pass

    row["_raw"] = {
        "calendar_id": calendar_id,
        "calendar_name": calendar_name,
        "calendar_tier": calendar_tier,
        "ics_description": description,
    }
    return row


def fetch_via_ics(calendar_id, calendar_name, calendar_tier, session):
    resp = session.get(ICS_ENDPOINT, params={"entity": "calendar", "id": calendar_id}, timeout=20)
    resp.raise_for_status()
    lines = _unfold_ics(resp.text)

    rows = []
    block = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            block = []
        elif line == "END:VEVENT":
            if block is not None:
                rows.append(_from_ics_vevent(block, calendar_id, calendar_name, calendar_tier))
            block = None
        elif block is not None:
            block.append(line)
    return rows


def fetch_calendar(calendar_id, calendar_name, calendar_tier, session=None):
    session = session or requests.Session()
    try:
        rows = fetch_via_json(calendar_id, calendar_name, calendar_tier, session)
        if rows:
            return rows, "json"
    except (requests.RequestException, ValueError) as exc:
        print("  luma json endpoint failed for {}: {}".format(calendar_id, exc))
    return fetch_via_ics(calendar_id, calendar_name, calendar_tier, session), "ics"


def fetch_all(calendars, session=None):
    session = session or requests.Session()
    all_rows = []
    for cal in calendars:
        rows, via = fetch_calendar(cal["id"], cal.get("name"), cal.get("tier"), session=session)
        print("  {} ({}) via {}: {} events".format(cal.get("name", cal["id"]), cal["id"], via, len(rows)))
        all_rows.extend(rows)
    return all_rows
