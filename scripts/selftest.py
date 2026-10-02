#!/usr/bin/env python3
"""Offline self-tests, run by scripts/check.sh. No network, no Supabase. Plain asserts — each test
guards a bug that already happened once."""
import copy
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import manual_guard  # noqa: E402
from score import scorer, verdicts  # noqa: E402

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def spec_enum(field):
    """Allowed values for `field`, parsed from SPEC.md §2's schema block."""
    text = (ROOT / "SPEC.md").read_text(encoding="utf-8")
    block = text[text.index("## §2 EVENT SCHEMA"):]
    block = block[block.index("```"):]
    block = block[: block.index("```", 3)]
    lines = block.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"\s*" + field + r"\b", line):
            window = "\n".join(lines[i:i + 4])
            m = re.search(r"[(#]\s*((?:[a-z_]+\s*\|\s*)+[a-z_]+)", window)
            if m:
                return tuple(v.strip() for v in m.group(1).split("|"))
    raise AssertionError("could not find an enum for {!r} in SPEC.md §2".format(field))


@test
def scorer_enums_match_spec():
    for field, allowed in scorer.ALLOWED_ENUMS.items():
        assert set(spec_enum(field)) == set(allowed), (
            "{}: SPEC.md §2 allows {} but scorer.ALLOWED_ENUMS has {}".format(field, spec_enum(field), allowed))


@test
def scorer_refuses_incomplete_table():
    saved = scorer.PRIOR_HOOK_MULT.pop("person")
    try:
        try:
            scorer.assert_tables_complete()
        except RuntimeError:
            return
        raise AssertionError("scorer accepted a prior_hook table with no 'person' entry")
    finally:
        scorer.PRIOR_HOOK_MULT["person"] = saved


@test
def scorer_rejects_unknown_enum_value_instead_of_defaulting():
    row = {"format": "mixer", "participant": True, "target_proximity": "some", "prior_hook": "persn",
           "duration_hr": 2, "_raw": {}}
    try:
        scorer.score_row(row)
    except ValueError:
        return
    raise AssertionError("a misspelled prior_hook was silently scored as a default")


@test
def person_hook_outranks_topic_and_none():
    def p(hook):
        row = {"format": "workshop", "participant": True, "target_proximity": "some",
               "cohort_saturation": "none", "prior_hook": hook, "duration_hr": 2, "_raw": {}}
        return scorer.score_row(row)["predicted_p"]
    assert p("person") > p("topic") > p("none"), (p("person"), p("topic"), p("none"))


def _manual_row(**over):
    row = {"id": "x", "name": "Hand Set", "reachable": True, "cost_blocks": 1.0, "predicted_p": 0.4,
           "_manual": {"fields": ["reachable", "cost_blocks", "predicted_p"], "set_by": "test"}}
    row.update(over)
    return row


@test
def manual_guard_restores_overwritten_fields_and_records_shadow():
    row = _manual_row()
    report = manual_guard.Report()
    with report.protect([row], "test-stage"):
        row["reachable"] = None
        row["cost_blocks"] = 2.0
        row["predicted_p"] = 0.1
    assert (row["reachable"], row["cost_blocks"], row["predicted_p"]) == (True, 1.0, 0.4)
    assert set(row["_manual"]["shadow"]) == {"reachable", "cost_blocks", "predicted_p"}
    assert row["_manual"]["shadow"]["cost_blocks"]["would_have_written"] == 2.0
    assert len(report.blocked) == 3


@test
def manual_guard_leaves_unprotected_fields_alone_and_reports_zero_blocked():
    row = _manual_row()
    report = manual_guard.Report()
    with report.protect([row], "test-stage"):
        row["verdict"] = "go"
    assert row["verdict"] == "go" and not report.blocked and report.agreed == 3


@test
def manual_guard_restores_even_if_the_stage_raises():
    row = _manual_row()
    report = manual_guard.Report()
    try:
        with report.protect([row], "test-stage"):
            row["reachable"] = False
            raise RuntimeError("stage crashed")
    except RuntimeError:
        pass
    assert row["reachable"] is True


@test
def manual_guard_carries_values_across_an_ingest_replacement():
    old = _manual_row()
    fresh = {"id": "x", "name": "Hand Set", "reachable": None, "cost_blocks": None, "predicted_p": None}
    report = manual_guard.Report()
    new = report.carry_forward(old, copy.deepcopy(fresh))
    assert (new["reachable"], new["cost_blocks"], new["predicted_p"]) == (True, 1.0, 0.4)
    assert new["_manual"]["fields"] == old["_manual"]["fields"]


@test
def manual_guard_refuses_a_malformed_manual_record():
    try:
        manual_guard.protected_fields({"name": "bad", "_manual": {"fields": "reachable"}})
    except ValueError:
        return
    raise AssertionError("malformed _manual.fields was accepted")


def _cand(eid, start, p, cost=0.5, duration=2, end=None, **over):
    row = {"id": eid, "name": eid, "start": start, "end": end, "duration_hr": duration,
           "predicted_p": p, "cost_blocks": cost, "confidence": 1.0, "reachable": True,
           "participant": True, "target_proximity": "some", "_raw": {}, "host_names": [eid],
           "source": "luma"}
    row.update(over)
    return row


@test
def overlapping_events_cannot_both_be_go_even_with_no_end_time():
    # Both rows have end=None — the real Builder Night / Camp AI shape. Zero-length intervals used
    # to compare as non-overlapping, so both came out GO.
    a = _cand("A", "2026-10-07T00:30:00Z", 0.60)
    b = _cand("B", "2026-10-07T00:30:00Z", 0.50)
    verdicts.resolve([a, b])
    assert (a["verdict"], b["verdict"]) == ("go", "skip"), (a["verdict"], b["verdict"])
    assert b["primary_reason"] == "conflict" and b["conflict_with"]["id"] == "A"


@test
def partial_overlap_is_a_conflict_but_back_to_back_is_not():
    a = _cand("A", "2026-10-07T00:00:00Z", 0.60, duration=2)
    b = _cand("B", "2026-10-07T01:00:00Z", 0.50, duration=2)   # starts an hour into A
    c = _cand("C", "2026-10-07T02:00:00Z", 0.40, duration=2)   # starts exactly when A ends
    verdicts.resolve([a, b, c])
    assert b["primary_reason"] == "conflict", b["verdict"]
    assert c["verdict"] != "skip" or c["primary_reason"] != "conflict"


@test
def a_conflict_loser_does_not_consume_a_quota_slot():
    a = _cand("A", "2026-10-07T00:00:00Z", 0.70)
    b = _cand("B", "2026-10-07T00:00:00Z", 0.60)   # loses to A, must not use a slot
    c = _cand("C", "2026-10-08T00:00:00Z", 0.50)
    verdicts.resolve([a, b, c])
    quota = verdicts.DEFAULT_SLOT_QUOTA
    assert quota >= 2
    assert (a["verdict"], c["verdict"]) == ("go", "go"), (a["verdict"], b["verdict"], c["verdict"])


@test
def a_confirmed_rsvp_beats_a_higher_scored_unconfirmed_event():
    a = _cand("A", "2026-10-07T00:00:00Z", 0.90)
    b = _cand("B", "2026-10-07T00:00:00Z", 0.35, rsvp_state="confirmed")
    verdicts.resolve([a, b])
    assert b["verdict"] == "go" and a["primary_reason"] == "conflict"
    assert a["conflict_with"]["kind"] == "confirmed"


def _scored(**over):
    row = {"id": "u", "name": "u", "start": "2026-10-07T00:30:00Z", "duration_hr": 2, "format": "workshop",
           "participant": True, "target_proximity": "high", "cohort_saturation": "none",
           "prior_hook": "none", "source": "luma", "host_names": ["u"], "_raw": {}}
    row.update(over)
    return scorer.score_row(row)


@test
def unknown_distance_is_neutral_not_free_and_not_worst_case():
    unknown = _scored(bart_walk_min=None, reachable=None)
    far = _scored(bart_walk_min=240, reachable=False)
    near = _scored(bart_walk_min=5, reachable=True)
    assert unknown["cost_blocks"] == scorer.NEUTRAL_PRIOR_COST_BLOCKS
    assert near["cost_blocks"] < unknown["cost_blocks"] < far["cost_blocks"] + 1e-9
    assert unknown["cost_blocks"] < verdicts.COST_DOWNGRADES_TO_PART
    assert unknown["_raw"]["cost_blocks_source"] == "neutral_prior"


@test
def unknown_distance_is_not_treated_as_unreachable_by_verdicts():
    unknown = _scored(bart_walk_min=None, reachable=None)
    unknown["id"] = "unknown-loc"
    verdicts.resolve([unknown])
    assert unknown["verdict"] not in ("suppressed", "go_if"), unknown["verdict"]
    assert unknown["cost_blocks"] < verdicts.UNREACHABLE_COST_BLOCKS


@test
def unknown_distance_lowers_confidence():
    known = _scored(bart_walk_min=5, reachable=True)
    unknown = _scored(bart_walk_min=None, reachable=None)
    assert unknown["confidence"] < known["confidence"]


@test
def a_stale_stored_cost_is_recomputed_unless_marked_manual():
    stale = _scored(bart_walk_min=5, reachable=True, cost_blocks=2.0)
    assert stale["cost_blocks"] == 0.0 and stale["_raw"]["cost_blocks_source"] == "estimated"
    kept = _scored(bart_walk_min=5, reachable=True, cost_blocks=1.5,
                   _manual={"fields": ["cost_blocks"], "set_by": "test"})
    assert kept["cost_blocks"] == 1.5 and kept["_raw"]["cost_blocks_source"] == "manual"


@test
def slot_ranking_uses_value_not_value_minus_cost():
    # 0.80 at cost 1.5 must beat 0.42 at cost 0.5 for the only slot. Under p - cost it lost.
    high = _cand("HIGH", "2026-10-07T00:00:00Z", 0.80, cost=1.5)
    cheap = _cand("CHEAP", "2026-10-08T00:00:00Z", 0.42, cost=0.5)
    saved = verdicts._load_quota_overrides
    verdicts._load_quota_overrides = lambda: {"2026-W41": 1}
    try:
        verdicts.resolve([high, cheap])
    finally:
        verdicts._load_quota_overrides = saved
    assert high["verdict"] in ("go", "part") and cheap["primary_reason"] == "quota_full", (
        high["verdict"], cheap["verdict"], cheap["primary_reason"])


@test
def cost_breaks_ties_between_equal_value_events():
    a = _cand("A", "2026-10-07T00:00:00Z", 0.50, cost=1.0)
    b = _cand("B", "2026-10-08T00:00:00Z", 0.50, cost=0.5)
    saved = verdicts._load_quota_overrides
    verdicts._load_quota_overrides = lambda: {"2026-W41": 1}
    try:
        verdicts.resolve([a, b])
    finally:
        verdicts._load_quota_overrides = saved
    assert b["verdict"] == "go" and a["primary_reason"] == "quota_full"


def main():
    failures = []
    for fn in TESTS:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — report every failure, not just the first
            failures.append("{}: {}: {}".format(fn.__name__, type(exc).__name__, exc))
    if failures:
        raise SystemExit("SELFTEST FAILED ({} of {}):\n  ".format(len(failures), len(TESTS)) + "\n  ".join(failures))
    print("selftests passed ({} tests)".format(len(TESTS)))


if __name__ == "__main__":
    main()
