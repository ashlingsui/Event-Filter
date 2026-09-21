"""Speaker-level enrichment — RECORDED-BUT-UNWEIGHTED (SPEC.md §1c "record early, weight late"),
added 2026-09-21. Not read anywhere in score/scorer.py; weight stays 0 until the "host prestige /
speaker seniority predicts outcomes" hypothesis independently clears >=3 supporting events
(capture/schema.py:HYPOTHESIS_THRESHOLD).

Why this exists distinct from host_tier: "is the host prestigious" is a blunt instrument — a small
company's own event that happens to land a well-known speaker beats a generic tier1_vc mixer, and
only speaker-level data can see that difference (her framing, 2026-09-21).

Two pieces, same split as everywhere else in this codebase:
  fetch_description() — real, general, needs no API key. Pulls a Luma event's own page (not just
    the calendar-list JSON, which only gives a short summary) and flattens its rich-text
    description. Verified live 2026-09-21 against the one past event still reachable by URL —
    Luma pages seem to survive past their event date, but "backfill while the pages are still up"
    is a closing window, not a standing guarantee; don't assume it holds indefinitely.
  extract_speakers_via_api() — needs real language understanding (arbitrary phrasing: "Jane Doe,
    Head of X at Y" vs "joined by Jane from Y" vs no employer stated at all), so this is a real
    Anthropic API call gated on ANTHROPIC_API_KEY, degrading to None (not a guess) without one —
    same pattern as enrich/llm_enrich.py and capture/extract.py.
"""
import json
import os
import re

import requests

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EventFilterBot/1.0)"}
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)


def _flatten_richtext(node, out):
    if isinstance(node, dict):
        if node.get("type") == "text":
            out.append(node.get("text", ""))
        for child in node.get("content") or []:
            _flatten_richtext(child, out)
        if node.get("type") == "paragraph":
            out.append("\n")
    elif isinstance(node, list):
        for n in node:
            _flatten_richtext(n, out)


def fetch_description(url, session=None):
    """Full event-page description text. Returns None if the page is gone, redirected somewhere
    unparseable, or has no description_mirror (external/non-Luma events, mostly)."""
    session = session or requests.Session()
    resp = session.get(url, headers=_HEADERS, timeout=20, allow_redirects=True)
    resp.raise_for_status()
    match = _NEXT_DATA_RE.search(resp.text)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return None
    initial = data.get("props", {}).get("pageProps", {}).get("initialData", {}).get("data", {})
    mirror = initial.get("description_mirror")
    if not mirror:
        return None
    out = []
    _flatten_richtext(mirror, out)
    return "".join(out).strip()


FIELD_INSTRUCTIONS = """\
Extract every named speaker/presenter mentioned in this event description, with their current
employer if stated. Do not include the event's hosts/sponsors themselves (e.g. the company whose
name is in the event title) unless they are also individually named as a speaker with a role.
Never guess an employer that isn't stated or clearly, directly implied — null beats a wrong guess.

Respond with ONLY a JSON array: [{"name": "...", "title": "... or null", "employer": "... or null"}]
If no named speakers are mentioned, respond with [].
"""


def build_prompt(description_text):
    return "{}\n\nEvent description:\n{}".format(FIELD_INSTRUCTIONS, description_text)


def call_model(description_text, api_key, model=DEFAULT_MODEL):
    resp = requests.post(
        API_URL,
        headers={"x-api-key": api_key, "anthropic-version": API_VERSION, "content-type": "application/json"},
        json={"model": model, "max_tokens": 500, "messages": [{"role": "user", "content": build_prompt(description_text)}]},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return "".join(block.get("text", "") for block in data.get("content", []))


_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def parse_speakers(text):
    match = _JSON_ARRAY_RE.search(text)
    if not match:
        return None
    try:
        speakers = json.loads(match.group(0))
    except ValueError:
        return None
    return speakers if isinstance(speakers, list) else None


def extract_speakers_via_api(description_text, model=DEFAULT_MODEL):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key or not description_text:
        return None
    return parse_speakers(call_model(description_text, api_key, model=model))


def enrich_row(row, session=None):
    """Fetches + extracts for one row where possible. Only Luma URLs have description_mirror;
    everything else is left alone (speakers stays [])."""
    if row.get("source") != "luma" or not row.get("url") or "luma.com" not in row["url"] and "lu.ma" not in row["url"]:
        return row
    description = fetch_description(row["url"], session=session)
    if not description:
        return row
    row["_raw"]["description_text"] = description
    speakers = extract_speakers_via_api(description)
    if speakers:
        row["speakers"] = speakers
        row["_raw"]["speakers_source"] = DEFAULT_MODEL
    return row
