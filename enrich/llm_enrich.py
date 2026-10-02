"""Judgment half of step 2 (Enrich): participant, target_proximity, format, cohort_saturation,
prior_hook. These can't be computed from geometry, so they're an LLM classification pass over
each event's scraped text, grounded in Ashling's profile (BUILD_HANDOFF.md) and the exact field
definitions SPEC.md §2 locks in.

Runs only on rows geocode.py did NOT already reject (reachable is True or still unknown) — see
enrich_events.py for why. Requires ANTHROPIC_API_KEY; skips cleanly and leaves fields null
without one, rather than guessing.
"""
import json
import os
import re
import time

import requests

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
RATE_LIMIT_SEC = 0.3

PROFILE_CONTEXT = """\
Ashling Sui — Haas MBA class of 2028 (MBA1, fall recruiting now). Previously Meituan product
strategy and Deloitte consulting, both Shanghai. Targeting Big Tech PM / big-startup AI PM roles.
Needs visa sponsorship, which filters most seed-stage startups as employers but NOT as sources of
build inspiration. Lives in Berkeley, does not drive. Current bottleneck is her own portfolio
website/projects (proof-of-work) — resume is done, applications are out. She is a BUILDER: she
gets value from events where she can participate hands-on (build nights, hackathons, demos), not
just watch. EWMBA/EMBA Haas events are networking events (those classmates currently work at
target companies); full-time MBA cohort events are social, not career events."""

FIELD_INSTRUCTIONS = """\
Classify this event on exactly these six fields. Base every answer only on the event text given
— do not assume facts not in it. If the text doesn't support a confident answer, use the stated
default; do not guess to fill a field.

participant (bool): Can Ashling legitimately DO the thing this event is for — build, demo, code,
  workshop along — versus only watch/listen? true for build nights, hackathons, workshops, demo
  days. false for panels, firesides, lectures, lectures-with-Q&A, lead-gen mixers where she'd only
  be a spectator. Default false if unclear.

target_proximity (one of: none, some, high, wrong_ladder): Density of people who are CURRENTLY
  INSIDE Ashling's target companies (big tech / big-startup AI PM), or one hop out, likely to be
  in the room — not seniority, not affiliation. A VC/founder-only event where attendees are ahead
  of her on a ladder she isn't climbing is wrong_ladder (VCs and founders are not her target
  employers). An AI infra/tooling company's own event (their staff + their users) is "high" if the
  company itself is a plausible target employer or its users skew PM/industry. Default "none" if
  the text gives no real signal.

format (one of: build_night, hackathon, demo_day, workshop, panel, fireside, mixer, lecture,
  class, office_hours): Pick the single closest match from the event's name/description. Default "mixer" if
  genuinely ambiguous.

cohort_saturation (one of: none, some, high): Share of the room Ashling would likely already know.
  "high" only for Haas full-time MBA cohort-only social events. Company/industry meetups, other
  schools' clubs, and public tech events default to "none". Default "none" if unclear.

prior_hook (one of: none, topic): Whether Ashling plausibly already has a content-level hook into
  this specific event's topic (she actively uses the product/tool the event is about — e.g.
  Anthropic/Claude, OpenRouter, Codex/OpenAI dev tools — or the topic is squarely AI product/PM,
  her own domain). This can only detect a TOPIC hook from event content; it can never detect a
  PERSON hook (whether she has personally met a specific host) — leave prior_hook "none" even if a
  person hook might exist; that requires her own input, not text classification. Default "none".

host_tier (one of: tier1_vc, scaled_co, startup, student_club, unknown): What kind of
  organization is actually hosting/running this — not who's speaking at it. A name-brand VC fund
  or accelerator's own event (Berkeley SkyDeck, Afore Capital) is tier1_vc. A company with real
  operating scale (Anthropic, Stripe) is scaled_co. A smaller company or well-funded startup
  running its own event (OpenRouter) is startup. A Haas/CampusGroups student club is student_club.
  Default "unknown" if the hosting organization's type genuinely isn't discernible from the text —
  this field is RECORDED BUT NOT YET WEIGHTED (SPEC.md §1c), so a wrong guess here costs nothing
  today but pollutes it later; still don't guess past what the text supports.

Respond with ONLY a JSON object, no prose, matching exactly:
{"participant": true|false, "target_proximity": "...", "format": "...", "cohort_saturation": "...", "prior_hook": "...", "host_tier": "..."}
"""

_VALID = {
    "target_proximity": {"none", "some", "high", "wrong_ladder"},
    "format": {
        "build_night", "hackathon", "demo_day", "workshop", "panel", "fireside", "mixer",
        "lecture", "class", "office_hours",
    },
    "cohort_saturation": {"none", "some", "high"},
    "prior_hook": {"none", "topic"},
    "host_tier": {"tier1_vc", "scaled_co", "startup", "student_club", "unknown"},
}

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _event_text(row):
    lines = [
        "Name: {}".format(row.get("name") or "(none)"),
        "Source: {}".format(row.get("source")),
        "Venue: {}".format(row.get("venue") or "(unknown)"),
        "City: {}".format(row.get("city") or "(unknown)"),
        "Hosts: {}".format(", ".join(row.get("host_names") or []) or "(none listed)"),
    ]
    raw = row.get("_raw") or {}
    description = raw.get("ld_json", {}).get("description") if isinstance(raw.get("ld_json"), dict) else None
    description = description or raw.get("category") or raw.get("ics_description")
    if description:
        lines.append("Description: {}".format(description[:800]))
    calendar_name = raw.get("calendar_name")
    if calendar_name:
        lines.append("Calendar: {}".format(calendar_name))
    return "\n".join(lines)


def build_prompt(row):
    return "{}\n\nEvent to classify:\n{}\n\n{}".format(PROFILE_CONTEXT, _event_text(row), FIELD_INSTRUCTIONS)


def call_model(prompt, api_key, model=DEFAULT_MODEL):
    resp = requests.post(
        API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return "".join(block.get("text", "") for block in data.get("content", []))


def parse_judgment(text):
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        return None
    try:
        judgment = json.loads(match.group(0))
    except ValueError:
        return None
    for field, allowed in _VALID.items():
        if judgment.get(field) not in allowed:
            return None
    if not isinstance(judgment.get("participant"), bool):
        return None
    return judgment


def enrich_row(row, api_key, model=DEFAULT_MODEL):
    prompt = build_prompt(row)
    try:
        text = call_model(prompt, api_key, model=model)
    except requests.RequestException as exc:
        row["_raw"]["llm_enrichment_error"] = str(exc)
        return False
    judgment = parse_judgment(text)
    if judgment is None:
        row["_raw"]["llm_enrichment_error"] = "unparseable response: {}".format(text[:200])
        return False
    row["participant"] = judgment["participant"]
    row["target_proximity"] = judgment["target_proximity"]
    row["format"] = judgment["format"]
    row["cohort_saturation"] = judgment["cohort_saturation"]
    row["prior_hook"] = judgment["prior_hook"]
    row["host_tier"] = judgment["host_tier"]
    row["_raw"]["enrichment_source"] = model
    return True


def apply_manual(rows, judgments_path, source_tag):
    """Apply a hand-produced judgments file (same shape as parse_judgment's output) instead of
    calling the API — for a one-time pass done when no ANTHROPIC_API_KEY is available. Goes
    through the same validation as the automated path so a malformed entry is skipped, not
    silently trusted."""
    with open(judgments_path) as f:
        judgments = json.load(f)["judgments"]

    by_id = {row["id"]: row for row in rows}
    applied = 0
    for event_id, judgment in judgments.items():
        row = by_id.get(event_id)
        if row is None:
            continue
        validated = parse_judgment(json.dumps(judgment))
        if validated is None:
            row["_raw"]["llm_enrichment_error"] = "manual judgment failed validation: {}".format(judgment)
            continue
        row["participant"] = validated["participant"]
        row["target_proximity"] = validated["target_proximity"]
        row["format"] = validated["format"]
        row["cohort_saturation"] = validated["cohort_saturation"]
        row["prior_hook"] = validated["prior_hook"]
        row["host_tier"] = validated["host_tier"]
        row["_raw"]["enrichment_source"] = source_tag
        applied += 1
    print("  manual pass: {}/{} judgments applied from {}".format(applied, len(judgments), judgments_path))
    return rows


def enrich_all(rows, session=None, model=DEFAULT_MODEL):
    """Returns (rows, ran, eligible_count). `ran` is False when ANTHROPIC_API_KEY was absent and
    the LLM pass was skipped — the caller (enrich_events.py) decides what to do about that; this
    function's job is only to report it accurately, not to decide whether skipping is fatal."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    eligible = [r for r in rows if r.get("reachable") is not False]
    if not api_key:
        print("  ANTHROPIC_API_KEY not set — skipping LLM pass ({} rows eligible, left null)".format(len(eligible)))
        return rows, False, len(eligible)

    ok = 0
    for row in eligible:
        if enrich_row(row, api_key, model=model):
            ok += 1
        time.sleep(RATE_LIMIT_SEC)
    print("  llm pass: {}/{} eligible rows classified ({} skipped as unreachable)".format(
        ok, len(eligible), len(rows) - len(eligible)
    ))
    return rows, True, len(eligible)
