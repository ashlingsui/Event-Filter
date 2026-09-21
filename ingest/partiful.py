"""Partiful ingest, two sources:

1. `fetch_all` — per-URL scrape (og:* meta + schema.org JSON-LD) for events hand-collected in
   config (config/calendars.json → partiful_urls). Still needed: there is no calendar/search
   feed that covers a specific host or a specific series like Tech Week.

2. `fetch_explore` — partiful.com/explore, a genuine public "Browse and find local events" page
   discovered 2026-09-17. No auth. `partiful.com/events` (the obvious guess) is a dead end — it's
   an empty personalized SPA shell with no server data (`pageProps: {}`) until a logged-in user's
   client JS fetches their own feed. `/explore` instead ships real data server-side in
   `__NEXT_DATA__`: a small curated "trending" carousel (~5 events) per region, with SF as one of
   three regions (alongside NYC, LA) — all returned in one response regardless of caller IP, no
   geo-targeting needed. It skews general-social (block parties, run clubs, popups), not
   tech/build events, and it is NOT exhaustive — treat it as a supplementary discovery trickle,
   the Partiful analogue of Luma's `lu.ma/sf` calendar-discovery page, not a replacement for
   hand-collected URLs.
"""
import json
import re

import requests

from .schema import new_event
from .util import duration_hr_from_iso

_META_RE = re.compile(
    r'<meta[^>]+property=["\']og:([a-zA-Z:_]+)["\'][^>]+content=["\']([^"\']*)["\']', re.IGNORECASE
)
_LD_JSON_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL
)
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EventFilterBot/1.0)"}
EXPLORE_URL = "https://partiful.com/explore"


def _extract_og(html_text):
    return {m.group(1): m.group(2) for m in _META_RE.finditer(html_text)}


def _extract_ld_event(html_text):
    for match in _LD_JSON_RE.finditer(html_text):
        try:
            data = json.loads(match.group(1))
        except ValueError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if isinstance(candidate, dict) and "Event" in str(candidate.get("@type", "")):
                return candidate
    return None


def _slug(url):
    return url.rstrip("/").split("/")[-1] or url


def fetch_event(url, session=None):
    session = session or requests.Session()
    resp = session.get(url, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    html_text = resp.text

    og = _extract_og(html_text)
    ld = _extract_ld_event(html_text) or {}

    row = new_event()
    row["id"] = "partiful:{}".format(_slug(url))
    row["source"] = "partiful"
    row["url"] = og.get("url") or url
    row["name"] = ld.get("name") or og.get("title")
    row["start"] = ld.get("startDate")
    row["end"] = ld.get("endDate")
    row["duration_hr"] = duration_hr_from_iso(row["start"], row["end"])

    location = ld.get("location")
    if isinstance(location, dict):
        row["venue"] = location.get("name")
        address = location.get("address")
        if isinstance(address, dict):
            row["city"] = address.get("addressLocality")
        geo = location.get("geo") or {}
        row["lat"] = geo.get("latitude")
        row["lng"] = geo.get("longitude")

    row["_raw"] = {"og": og, "ld_json": ld or None}
    return row


def fetch_all(urls, session=None):
    session = session or requests.Session()
    rows = []
    for url in urls:
        try:
            rows.append(fetch_event(url, session=session))
        except requests.RequestException as exc:
            print("  partiful fetch failed for {}: {}".format(url, exc))
    print("  partiful: {} events from {} configured urls".format(len(rows), len(urls)))
    return rows


def _extract_next_data(html_text):
    match = _NEXT_DATA_RE.search(html_text)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except ValueError:
        return {}


def _host_names_from_label(host_label):
    label = re.sub(r"(?i)^hosted by:?\s*", "", host_label or "").strip()
    if not label:
        return []
    return [n.strip() for n in re.split(r"\s*(?:,|&| and )\s*", label) if n.strip()]


def _from_explore_event(event, region):
    row = new_event()
    event_id = event.get("id")
    row["id"] = "partiful:{}".format(event_id)
    row["source"] = "partiful"
    row["url"] = "https://partiful.com/e/{}".format(event_id)
    row["name"] = event.get("title")
    row["start"] = event.get("startDate")
    row["end"] = event.get("endDate")
    row["duration_hr"] = duration_hr_from_iso(row["start"], row["end"])

    location = event.get("locationInfo") or {}
    maps_info = location.get("mapsInfo") or {}
    address_lines = maps_info.get("addressLines") or []
    row["venue"] = (
        maps_info.get("name") or location.get("displayName") or (", ".join(address_lines) or None)
    )
    city_source = address_lines[-1] if address_lines else location.get("approximateLocation")
    if city_source:
        row["city"] = city_source.split(",")[0].strip()

    row["host_names"] = _host_names_from_label(event.get("hostName"))
    row["size"] = event.get("goingGuestCount")

    row["_raw"] = {
        "discovery_region": region,
        "neighborhood": location.get("neighborhood"),
        "address_lines": address_lines,
        "google_maps_url": maps_info.get("googleMapsUrl"),
        "apple_maps_url": maps_info.get("appleMapsUrl"),
        "guest_counts": {
            "interested": event.get("interestedGuestCount"),
            "going": event.get("goingGuestCount"),
            "approved": event.get("approvedGuestCount"),
            "maybe": event.get("maybeGuestCount"),
            "waitlist": event.get("waitlistGuestCount"),
        },
        "is_public": event.get("isPublic"),
        "status": event.get("status"),
    }
    return row


def fetch_explore(session=None, regions=("SF",)):
    session = session or requests.Session()
    resp = session.get(EXPLORE_URL, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    data = _extract_next_data(resp.text)
    sections = ((data.get("props") or {}).get("pageProps") or {}).get("trendingSections", {})

    rows = []
    for region in regions:
        section = sections.get(region) or {}
        for item in section.get("items", []):
            event = item.get("event")
            if event:
                rows.append(_from_explore_event(event, region))
    print("  partiful explore: {} events from {} region(s)".format(len(rows), len(regions)))
    return rows
