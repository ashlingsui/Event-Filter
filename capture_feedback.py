#!/usr/bin/env python3
"""Event Filter — step 4: capture, the read-back loop (SPEC.md §1c).

Chat is the input. Give it an event id and what she said, in her own words — not a form.

Usage:
    python3 capture_feedback.py <event_id> "<free text>"

Needs ANTHROPIC_API_KEY to actually extract. Without one, this prints what would have happened
and does nothing — it does not guess at her words the way a human reviewer would need to.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from capture.extract import record_feedback


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 capture_feedback.py <event_id> \"<free text>\"")
        sys.exit(1)

    event_id, free_text = sys.argv[1], sys.argv[2]
    row, newly_actionable, used_api = record_feedback(event_id, free_text)

    if not used_api:
        print("ANTHROPIC_API_KEY not set — nothing extracted, nothing written.")
        print("(This is intentional: without a real read of her words, there is nothing honest")
        print(" to record. See capture/extract.py:apply_manual for the no-key workaround used")
        print(" when a human is doing the extraction in-session instead.)")
        sys.exit(0)

    print("Recorded onto {}:".format(event_id))
    for k, v in row.items():
        if k not in ("event_id",):
            print("  {}: {}".format(k, v))

    if newly_actionable:
        print("\nJust crossed the actionable threshold (still requires her approval to weight):")
        for h in newly_actionable:
            print("  - {} (supported by {} events)".format(h["hypothesis"], len(h["supporting_events"])))


if __name__ == "__main__":
    main()
