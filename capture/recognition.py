"""T+7 and T+30 capture — SPEC.md §1's "Three capture points" table. Distinct from
capture/extract.py's free-text pipeline: T+0/T+1 is free text (felt_score + a sentence, "chat is
the input"), but T+7 is explicitly specified as structured — "Three yes/no questions... recognition
not recall." Recall fails at a week out; showing her the scraped names and asking "any of these?"
survives. So this module does NOT run anything through an LLM — it assembles a recognition prompt
from data already on file and records plain yes/no (+ optional short note) answers directly.

T+30 is the batch sweep: whatever is STILL open at 30 days becomes `unknown`, per SPEC.md's
missing-data policy (unanswered = unknown, counted and displayed, never silently dropped or
treated as a de facto no).
"""
import datetime as dt

from .store import find_outcome_row, load_outcomes, save_outcomes

T7_DAYS = 7
T30_DAYS = 30

_STREAM_FIELDS = ("s1_pov", "s2_contact", "s3_build", "s4_cohort")


def _parse_date(s):
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        return None


def _is_pending(value):
    """A stream reads as still-open if it's never been set, or carries one of the placeholder
    strings this file already uses ('pending T+7') rather than a real true/false answer."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower().startswith("pending"):
        return True
    return False


def _row_is_open(row):
    return any(_is_pending(row.get(f)) for f in _STREAM_FIELDS)


def due_for_t7(today=None, outcomes_data=None):
    """Rows at least T7_DAYS past their event date that still have an open stream. Does not
    include rows already fully labeled (the three retrospective backfills), and does not include
    rows not yet 7 days out."""
    today = today or dt.date.today()
    data = outcomes_data or load_outcomes()
    due = []
    for row in data["rows"]:
        event_date = _parse_date(row.get("date"))
        if not event_date or not _row_is_open(row):
            continue
        if (today - event_date).days >= T7_DAYS:
            due.append(row)
    return due


def due_for_t30(today=None, outcomes_data=None):
    """The batch sweep: every row 30+ days out that's still open, regardless of whether a T+7
    check already ran on it. 'One screen, all rows, tick down' (SPEC.md §1) — this is the final
    pass, not a per-row reminder."""
    today = today or dt.date.today()
    data = outcomes_data or load_outcomes()
    due = []
    for row in data["rows"]:
        event_date = _parse_date(row.get("date"))
        if not event_date or not _row_is_open(row):
            continue
        if (today - event_date).days >= T30_DAYS:
            due.append(row)
    return due


def build_recognition_prompt(row):
    """What to actually show her for one row's T+7 check. Recognition material comes from
    whatever's already on file — the row's own speakers[]/contacts_forming[] if present (that's
    where a backfilled row like OpenRouter's carries them), else best-effort nothing (this session
    has no live events.json cross-reference for it — see the id-scheme mismatch flagged
    2026-09-21: events.json keys Luma rows by api_id, outcomes.json by URL slug)."""
    names = []
    for s in row.get("speakers") or []:
        label = s.get("name")
        if s.get("employer"):
            label += " ({})".format(s["employer"])
        names.append(label)
    for c in row.get("contacts_forming") or []:
        if c.get("who"):
            names.append(c["who"])

    return {
        "event_id": row.get("event_id"),
        "name": row.get("name"),
        "recognition_names": names,
        "questions": [
            {
                "field": "s2_contact",
                "prompt": "Any of these — have you exchanged messages since, or are they now warm in contacts.csv?",
                "shows": names,
            },
            {
                "field": "s1_pov",
                "prompt": "Can you name the specific claim, in writing somewhere (note, message, interview answer)?",
            },
            {
                "field": "s3_build",
                "prompt": "Did you start or ship something traceable to this event?",
            },
            {
                "field": "s4_cohort",
                "prompt": "Did this strengthen a friendship or cohort tie you care about?",
            },
        ],
    }


def record_answers(event_id, answers, details=None, note=None):
    """answers: {"s1_pov": bool, "s2_contact": bool, "s3_build": bool, "s4_cohort": bool} — any
    subset; unanswered fields stay as they were (still open, not forced to a value). details:
    optional {"s1_pov": "the actual claim...", ...} short text alongside the boolean, matching the
    s1_detail/s2_detail/... shape the backfilled rows already use. Computes `hit` and
    `label_status` once no field is still pending. Field corrections apply immediately, same as
    capture/extract.py's Recorded pane — these are facts, not proposals."""
    data = load_outcomes()
    row = find_outcome_row(data, event_id)
    if row is None:
        raise ValueError("no outcome row for {}".format(event_id))

    for field in _STREAM_FIELDS:
        if field in answers:
            row[field] = bool(answers[field])
            if details and field in details:
                row["{}_detail".format(field)] = details[field]
    if note:
        row.setdefault("t7_note", note)

    if not _row_is_open(row):
        row["hit"] = bool(row.get("s2_contact")) or bool(row.get("s3_build"))
        row["hit_basis"] = "s2_contact" if row.get("s2_contact") else ("s3_build" if row.get("s3_build") else "neither")
        row["label_status"] = "labeled"

    save_outcomes(data)
    return row


def close_out_t30(event_id):
    """The T+30 sweep's actual action on one row: any stream still pending becomes explicitly
    unknown (SPEC.md's missing-data policy), not left open forever and not quietly treated as a
    no. `hit` is computed from whatever DID get answered; unknown streams don't count as false."""
    data = load_outcomes()
    row = find_outcome_row(data, event_id)
    if row is None:
        raise ValueError("no outcome row for {}".format(event_id))

    for field in _STREAM_FIELDS:
        if _is_pending(row.get(field)):
            row[field] = "unknown"

    answered_hit_fields = [row.get("s2_contact"), row.get("s3_build")]
    if any(v == "unknown" for v in answered_hit_fields):
        row["hit"] = "unknown"
        row["label_status"] = "unknown"
    else:
        row["hit"] = bool(row.get("s2_contact")) or bool(row.get("s3_build"))
        row["label_status"] = "labeled"

    save_outcomes(data)
    return row
