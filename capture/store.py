"""Adopts data/outcomes.json as-is — she wrote its first row by hand 2026-09-20, before this
layer existed, and asked that its field names be adopted rather than a second store created.
Also owns data/pending_hypotheses.json, the durable home of the Suspected pane's counters."""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUTCOMES_PATH = ROOT / "data" / "outcomes.json"
HYPOTHESES_PATH = ROOT / "data" / "pending_hypotheses.json"


def load_outcomes():
    with OUTCOMES_PATH.open() as f:
        return json.load(f)


def save_outcomes(data):
    with OUTCOMES_PATH.open("w") as f:
        json.dump(data, f, indent=2)


def find_outcome_row(data, event_id):
    for row in data["rows"]:
        if row.get("event_id") == event_id:
            return row
    return None


def _new_hypotheses_store():
    return {
        "_note": (
            "Suspected-pane hypotheses (SPEC.md §1c). A hypothesis becomes actionable only after "
            "independently appearing across >= capture.schema.HYPOTHESIS_THRESHOLD events. "
            "protected=true hypotheses can never become actionable regardless of count — they read "
            "as touching the frozen outcome definition or its horizons."
        ),
        "hypotheses": {},
    }


def load_hypotheses():
    if HYPOTHESES_PATH.exists():
        with HYPOTHESES_PATH.open() as f:
            return json.load(f)
    return _new_hypotheses_store()


def save_hypotheses(data):
    with HYPOTHESES_PATH.open("w") as f:
        json.dump(data, f, indent=2)
