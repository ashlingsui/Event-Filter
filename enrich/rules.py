"""Tier 1 enrichment — deterministic, no model, no API key, no network call. SPEC.md §3c: "Most
classification here is keyword work... deterministic beats probabilistic for something this
mechanical." Runs over the same scraped text enrich/llm_enrich.py's _event_text() builds its
prompt from (name + description-ish _raw fields); it just classifies it with regex instead of a
model call.

Two things this sets:

1. `format` — single closest keyword match, same enum as the LLM/manual path. Deliberately
   conservative: unlike the LLM pass (which defaults to "mixer" when genuinely ambiguous), a rule
   that finds no match leaves `format` None. A rule is not a judgment call; guessing a default
   here would be exactly the "unknown scored as zero"-shaped mistake SPEC.md §3c exists to stop,
   one layer up.

2. `segments` — SPEC.md §3b's agenda parse: "first 30 minutes hanging out and meeting people,
   then about an hour of live demos" is parseable without a model. Top-level `format` remains the
   dominant segment (§3b); segments are additive, RECORDED-BUT-UNWEIGHTED — score/scorer.py's S3
   still reads top-level `format` only, not segments, until a later change wires §3b's
   segment-aware formula in.

Both fields are marked `source: "rule"` in `_raw` (`format_source`, `segments_source`) so they
stay distinguishable from an LLM judgment (`_raw.enrichment_source` = model name) or a hand-entered
one. Only ever FILLS a currently-null/empty field — never overwrites an existing value, same
non-destructive contract as llm_enrich.apply_manual().
"""
import re

import requests

from . import speakers

# Ordered most-distinctive-first; the first pattern that matches wins. A generic word like
# "meetup" is deliberately absent — on its own it says nothing about format, and guessing from it
# would be worse than leaving the field unknown.
FORMAT_KEYWORD_RULES = [
    ("hackathon", (r"\bhackathon\b", r"\bhack[\s-]?a[\s-]?thon\b")),
    ("demo_day", (r"\bdemo\s*day\b", r"\bdemo\s*night\b", r"\bshowcase\b")),
    ("build_night", (
        r"\bbuild\s*night\b", r"\bbuild[\s-]?a[\s-]?thon\b",
        r"\bhacking\s+session\b", r"\bco-?working\s+session\b",
    )),
    ("office_hours", (r"\boffice\s*hours?\b", r"\bask[\s-]?me[\s-]?anything\b", r"\bama\s+session\b")),
    ("workshop", (r"\bworkshop\b", r"\bhands-?on\s+(training|tutorial)\b", r"\btraining\s+session\b")),
    ("fireside", (r"\bfireside\b",)),
    ("class", (r"\bclass\s+session\b", r"\bcourse\s+session\b", r"\blecture\s+series\b")),
    ("panel", (r"\bpanel(\s+discussion)?\b",)),
    ("lecture", (r"\blecture\b", r"\bkeynote\b", r"\bguest\s+speaker\b", r"\btalk\s+by\b")),
    ("mixer", (r"\bmixer\b", r"\bhappy\s+hour\b", r"\bsocial\s+hour\b", r"\bnetworking\s+(event|night|reception)\b")),
]

# Narrower vocabulary than FORMAT_KEYWORD_RULES on purpose — a segment clause is a short phrase
# ("hanging out and meeting people"), not a full event description, so broader/softer signal words
# belong here even though they'd be too weak to classify a whole event's format.
SEGMENT_KIND_KEYWORD_RULES = [
    ("demo_day", (r"\bdemo(s)?\b", r"\bshowcase\b", r"\bpresentations?\b")),
    ("build_night", (r"\bbuild(ing)?\b", r"\bhack(ing)?\b", r"\bwork(ing)?\s+on\b", r"\bcod(e|ing)\b")),
    ("panel", (r"\bpanel\b", r"\bq\s*&\s*a\b", r"\bdiscussion\b")),
    ("lecture", (r"\btalk\b", r"\bkeynote\b", r"\bpresentation\b")),
    ("mixer", (
        r"\bhang(ing)?\s+out\b", r"\bmeet(ing)?\s+people\b", r"\bmingl(e|ing)\b",
        r"\bnetworking\b", r"\bsocial(izing)?\b", r"\bfood\s+and\s+drinks?\b",
    )),
]

_NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "half": 0.5}

_DURATION_RE = re.compile(
    r"\b(?P<num>\d+(?:\.\d+)?|a|an|one|two|three|four|half)\s*(?:-|\s)?\s*(?P<unit>hours?|hrs?|minutes?|mins?)\b",
    re.IGNORECASE,
)

# Splits an agenda description into clauses at explicit sequencing words and sentence boundaries —
# SPEC.md §3b's own example: "first 30 minutes hanging out and meeting people, then about an hour
# of live demos" splits at "then" into two independently-timed, independently-classified clauses.
_CLAUSE_SPLIT_RE = re.compile(r"(?:\bthen\b|\bfollowed by\b|[.;])", re.IGNORECASE)


def _duration_minutes(text):
    """First duration phrase in `text`, in minutes, or None."""
    m = _DURATION_RE.search(text)
    if not m:
        return None
    num_raw = m.group("num").lower()
    num = _NUMBER_WORDS.get(num_raw)
    if num is None:
        try:
            num = float(num_raw)
        except ValueError:
            return None
    unit = m.group("unit").lower()
    minutes = num * 60 if unit.startswith(("hour", "hr")) else num
    return round(minutes)


def _match_first(text, rules):
    for kind, patterns in rules:
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return kind
    return None


def classify_format(text):
    """A format string, or None — never a guessed default (see module docstring)."""
    if not text:
        return None
    return _match_first(text, FORMAT_KEYWORD_RULES)


def parse_segments(text):
    """One segment per clause that has BOTH a duration and a recognizable activity. A clause with
    only one of the two contributes nothing — partial information isn't a segment, it's noise."""
    if not text:
        return []
    segments = []
    for clause in _CLAUSE_SPLIT_RE.split(text):
        clause = clause.strip()
        if not clause:
            continue
        minutes = _duration_minutes(clause)
        kind = _match_first(clause, SEGMENT_KIND_KEYWORD_RULES)
        if minutes is not None and kind is not None:
            segments.append({"kind": kind, "duration_min": minutes, "source": "described"})
    return segments


def _event_text(row):
    """Same text source llm_enrich.py's _event_text() prompts from — Tier 1 and Tier 3 read the
    same scraped text, they just classify it differently."""
    parts = [row.get("name") or ""]
    raw = row.get("_raw") or {}
    description = raw.get("ld_json", {}).get("description") if isinstance(raw.get("ld_json"), dict) else None
    description = description or raw.get("category") or raw.get("ics_description")
    if description:
        parts.append(description)
    return "\n".join(p for p in parts if p)


def _fetched_event_text(row, session):
    """The event's own listing page, not just the calendar-list summary ingest captured — same
    fetch enrich/speakers.py already does for speaker extraction (plain HTTP GET + HTML/JSON
    parse, no model, no API key). The calendar-list text is often a short teaser with no agenda
    ("Get up-to-date information at: ...") — the agenda sentence SPEC.md §3b's segments example
    depends on usually only lives on the real page (description_mirror). Cached onto the row so a
    re-run doesn't re-fetch; a failed fetch (page gone, non-Luma URL, network error) just leaves
    the cache unset and Tier 1 falls back to the shorter ingest-time text."""
    raw = row.setdefault("_raw", {})
    if "description_mirror" in raw:
        return raw["description_mirror"] or ""
    url = row.get("url")
    if not url or session is None:
        return ""
    try:
        mirror = speakers.fetch_description(url, session=session)
    except requests.RequestException:
        mirror = None
    raw["description_mirror"] = mirror  # cache the miss too — don't refetch a dead page every run
    return mirror or ""


def enrich_row(row, session=None):
    """Mutates row in place. Returns True if it set anything. `session`, if given, lets this fetch
    the event's real listing page when the short ingest-time text yields no classification —
    purely to get more TEXT to pattern-match against; still no model, still deterministic."""
    text = _event_text(row)
    changed = False

    fmt = classify_format(text)
    segments = parse_segments(text)

    if (fmt is None or not segments) and session is not None:
        richer = _fetched_event_text(row, session)
        if richer:
            full_text = "{}\n{}".format(text, richer)
            if fmt is None:
                fmt = classify_format(full_text)
            if not segments:
                segments = parse_segments(full_text)

    if row.get("format") is None and fmt is not None:
        row["format"] = fmt
        row["_raw"]["format_source"] = "rule"
        changed = True

    if not row.get("segments") and segments:
        row["segments"] = segments
        row["_raw"]["segments_source"] = "rule"
        changed = True

    return changed


def enrich_all(rows, session=None):
    format_set = 0
    segments_set = 0
    for row in rows:
        had_format = row.get("format") is not None
        had_segments = bool(row.get("segments"))
        enrich_row(row, session=session)
        if not had_format and row.get("format") is not None:
            format_set += 1
        if not had_segments and row.get("segments"):
            segments_set += 1
    print("  rule pass: {} rows got format, {} rows got segments, from keyword rules alone".format(
        format_set, segments_set
    ))
    return rows
