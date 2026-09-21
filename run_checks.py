#!/usr/bin/env python3
"""Event Filter — step 4: T+7 / T+30 outcome checks (SPEC.md §1's capture-points table).

Prints what's due today. Recording answers is a separate call — see capture/recognition.py:
record_answers (T+7) and close_out_t30 (T+30) — this script only surfaces what needs a check,
since there's no UI yet to actually ask her.

Usage:
    python3 run_checks.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from capture.recognition import build_recognition_prompt, due_for_t7, due_for_t30


def main():
    t7 = due_for_t7()
    t30 = due_for_t30()

    print("T+7 checks due: {}".format(len(t7)))
    for row in t7:
        prompt = build_recognition_prompt(row)
        print("  - {} ({})".format(row["name"], row["event_id"]))
        print("    recognition names: {}".format(prompt["recognition_names"] or "(none logged)"))

    print("\nT+30 sweep due: {}".format(len(t30)))
    for row in t30:
        print("  - {} ({})".format(row["name"], row["event_id"]))

    if not t7 and not t30:
        print("Nothing due today.")


if __name__ == "__main__":
    main()
