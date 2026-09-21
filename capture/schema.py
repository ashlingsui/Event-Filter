"""Shapes for the read-back loop — SPEC.md §1c, added 2026-09-20.

Two panes, never mixed:
  Recorded  — extraction. Facts from what she said. She corrects these; corrections apply
              immediately, because they're facts.
  Suspected — inference. Patterns the system thinks it sees. She cannot approve these yet; they
              accumulate with a counter and become an actionable PROPOSAL only once the same
              hypothesis has been independently raised across >=3 events. Until then they change
              nothing and live on a visible pending-hypotheses list.

Mixing the panes is the named failure mode: a correct fact sitting next to a speculative inference
gets rubber-stamped along with it. They are kept in physically separate structures everywhere in
this module, not just styled differently by a future UI.
"""
import re

HYPOTHESIS_THRESHOLD = 3

# Enforces SPEC.md §1c's change-tier table at the logic layer, since there is no UI yet to grey
# anything out: "Outcome definition ... Never offerable. Not a setting." A hypothesis that reads as
# trying to touch the outcome definition (hit = S2 OR S3) or its horizons (T+0/T+1/T+7/T+30) can
# never become actionable, no matter how many events raise it — the ≥3 threshold does not apply to
# it, because it should never be applied to it. This is the worked example from §1c itself (the
# "SF doesn't matter" moment) generalized: the freeze has to survive contact with a good night.
_PROTECTED_PATTERNS = [
    re.compile(r"count(s|ed|ing)?\s+as\s+a?\s*hit", re.IGNORECASE),
    re.compile(r"redefin\w*\s+(the\s+)?(outcome|hit|label)", re.IGNORECASE),
    re.compile(r"what\s+counts\s+as\s+(a\s+)?(hit|outcome)", re.IGNORECASE),
    re.compile(r"\bT\+\s?(0|1|7|14|30)\b", re.IGNORECASE),
    re.compile(r"(change|adjust|move|shorten|extend|drop)\w*\s+.*\bhorizon", re.IGNORECASE),
]


def is_protected(hypothesis_text):
    return any(p.search(hypothesis_text or "") for p in _PROTECTED_PATTERNS)


def new_extraction_result():
    return {"recorded": {}, "suspected": []}
