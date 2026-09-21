"""Free text in, two panes out — SPEC.md §1c / LESSONS.md #19: "Chat is the input. Do not build
forms." She describes what happened in her own words; this extracts Recorded facts and flags
Suspected pattern-claims, never blending them. Mirrors enrich/llm_enrich.py's shape: a real
Anthropic API call gated on ANTHROPIC_API_KEY, with a manual fallback (apply_manual) for when one
isn't available, so the two paths produce identically-shaped output regardless of which ran.
"""
import json
import os
import re

import requests

from .schema import HYPOTHESIS_THRESHOLD, is_protected, new_extraction_result
from .store import load_hypotheses, load_outcomes, save_hypotheses, save_outcomes

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

FIELD_INSTRUCTIONS = """\
She is describing, in her own words, what happened at an event she attended (or what she now
believes as a result of several events). Extract into exactly two panes and never blend them.

RECORDED — only what she explicitly stated as fact about THIS event. Never infer, generalize, or
round up. If she didn't say it, leave the field null.
  felt_score: int 0-10, only if she gave or clearly implied a number.
  felt_note: her own words, kept close to verbatim — do not paraphrase away specifics. The
    phrasing itself is the data (LESSONS.md #19); do not compress "the demos worked and I used the
    tool that night" down to "positive experience."
  companions: names she mentioned attending with.
  trip_chained: true/false/null — was this already on a path she was taking for another reason.
  cost_blocks: 0 | 0.5 | 1 | 1.5 | 2 | null, only if directly statable from what she said.
  s1_pov: a specific claim she can name, or null.
  s2_contact: a specific contact/exchange she described, or null.
  s3_build: something she started or shipped because of this, or null.
  s4_cohort: a friendship/cohort tie strengthened, or null.
  contacts_forming: [{"who", "state", "note", "convening_power": true|false|null}] for anyone she
    mentioned meeting. convening_power is true only if she describes them as someone who could
    ASSEMBLE or introduce her to other valuable people/rooms (organizes things, runs a network,
    could invite her into something) — not merely someone senior or at a target company. That
    latter case is what target_proximity already measures; convening_power is a different,
    unweighted signal being recorded from scratch (LESSONS.md #23) — when in doubt, null, not false.

SUSPECTED — general pattern-level claims implied but not confirmed by this one event. Phrase each
as a claim that would read the same way if raised again about a totally different event, not as a
report of this specific instance (that belongs in recorded, not both places).
  Each: {"hypothesis": "<short, normalized, general claim>", "evidence": "<what she said that suggested it>"}

NEVER output a suspected hypothesis proposing to change what counts as a hit, or to change the
T+0/T+1/T+7/T+30 timing. Those are not extractable preferences — leave them out entirely, even as
"suspected." If what she said seems to be arguing for exactly that, capture the ARGUMENT as a
suspected hypothesis about something else defensible (e.g. "in-person events may carry more
unmodeled value than the cost model credits") rather than as a request to redefine the outcome.

Respond with ONLY a JSON object: {"recorded": {...}, "suspected": [...]}
"""


def build_prompt(free_text, event_context=""):
    parts = [FIELD_INSTRUCTIONS]
    if event_context:
        parts.append("Event context:\n{}".format(event_context))
    parts.append("What she said:\n{}".format(free_text))
    return "\n\n".join(parts)


_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def call_model(prompt, api_key, model=DEFAULT_MODEL):
    resp = requests.post(
        API_URL,
        headers={"x-api-key": api_key, "anthropic-version": API_VERSION, "content-type": "application/json"},
        json={"model": model, "max_tokens": 1000, "messages": [{"role": "user", "content": prompt}]},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return "".join(block.get("text", "") for block in data.get("content", []))


def parse_extraction(text):
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        return None
    try:
        result = json.loads(match.group(0))
    except ValueError:
        return None
    if "recorded" not in result or "suspected" not in result:
        return None
    return result


def extract_via_api(free_text, event_context="", model=DEFAULT_MODEL):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    text = call_model(build_prompt(free_text, event_context), api_key, model=model)
    return parse_extraction(text)


def _normalize_hypothesis(text):
    return re.sub(r"\s+", " ", text.strip().lower()).rstrip(".")


def seed_hypothesis(hypothesis_text, note=""):
    """Pre-registers a hypothesis at count 0 — a thing to watch for, not yet raised by any real
    event. Distinct from register_hypotheses, which always attaches a supporting event; this
    exists for exactly the case of deliberately opening a slot on the pending-hypothesis list
    before evidence exists, e.g. 'host prestige / speaker seniority predicts outcomes' the moment
    speakers[] starts being recorded — so there's somewhere for the first three supporting events
    to accumulate against once they happen."""
    store = load_hypotheses()
    key = _normalize_hypothesis(hypothesis_text)
    store["hypotheses"].setdefault(key, {
        "hypothesis": hypothesis_text,
        "protected": is_protected(hypothesis_text),
        "supporting_events": [],
        "evidence": [],
        "status": "pending",
        "seeded_note": note,
    })
    save_hypotheses(store)
    return store["hypotheses"][key]


def register_hypotheses(suspected, event_id, source_tag):
    """Appends each suspected hypothesis's supporting event to the durable pending-hypotheses
    store. Returns the list of hypotheses that just crossed the actionable threshold on THIS
    call (never auto-applies anything — SPEC.md §1c: a weight change still requires her explicit
    approval even after the threshold is cleared; this only makes the crossing visible)."""
    store = load_hypotheses()
    newly_actionable = []

    for item in suspected:
        text = item.get("hypothesis")
        if not text:
            continue
        protected = is_protected(text)
        key = _normalize_hypothesis(text)
        entry = store["hypotheses"].setdefault(key, {
            "hypothesis": text,
            "protected": protected,
            "supporting_events": [],
            "evidence": [],
            "status": "pending",
        })
        if protected:
            entry["protected"] = True

        if event_id not in entry["supporting_events"]:
            entry["supporting_events"].append(event_id)
            entry["evidence"].append({"event_id": event_id, "note": item.get("evidence"), "source": source_tag})

        count = len(entry["supporting_events"])
        if entry["protected"]:
            entry["status"] = "never_actionable"
        elif count >= HYPOTHESIS_THRESHOLD and entry["status"] != "actionable":
            entry["status"] = "actionable"
            newly_actionable.append(entry)
        elif entry["status"] != "actionable":
            entry["status"] = "pending"

    save_hypotheses(store)
    return newly_actionable


def apply_recorded(event_id, recorded, source_tag):
    """Applies Recorded-pane fields onto the outcomes.json row for event_id. Corrections apply
    immediately — this is a fact update, not a proposal. Creates the row if it doesn't exist yet."""
    data = load_outcomes()
    row = None
    for r in data["rows"]:
        if r.get("event_id") == event_id:
            row = r
            break
    if row is None:
        row = {"event_id": event_id}
        data["rows"].append(row)

    for field, value in recorded.items():
        if value is not None:
            row[field] = value
    row.setdefault("_capture_source", []).append(source_tag)

    save_outcomes(data)
    return row


def record_feedback(event_id, free_text, event_context="", model=DEFAULT_MODEL):
    """Full loop: extract (API if available), apply Recorded immediately, register Suspected
    against the pending-hypothesis counters. Returns (recorded_row, newly_actionable_hypotheses,
    used_api: bool)."""
    result = extract_via_api(free_text, event_context, model=model)
    used_api = result is not None
    if result is None:
        return None, [], False

    row = apply_recorded(event_id, result.get("recorded", {}), source_tag=model)
    newly_actionable = register_hypotheses(result.get("suspected", []), event_id, source_tag=model)
    return row, newly_actionable, used_api


def apply_manual(event_id, extraction, source_tag):
    """Same effect as record_feedback, for a hand-produced extraction result when no API key is
    available — mirrors enrich/llm_enrich.py:apply_manual's provenance pattern exactly."""
    row = apply_recorded(event_id, extraction.get("recorded", {}), source_tag=source_tag)
    newly_actionable = register_hypotheses(extraction.get("suspected", []), event_id, source_tag=source_tag)
    return row, newly_actionable
