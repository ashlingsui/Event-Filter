"""Per-event verdict + machine-readable reason codes, layered on top of scorer.py's predicted_p
and cost_blocks. Added 2026-09-18, revised 2026-09-20/21 — this is output format and decision
policy, not a label or scoring-formula change: predicted_p is read here, never written; cost_blocks
is read, and overwritten only by the unreachable-penalty rule below (itself a cost, not the value
model scorer.py owns).

Fixed reason-code set — do not add to this without saying so. One real gap remains flagged, not
silently patched: no code exists for "cleared the value bar but downgraded to partial attendance
by cost alone" (a go->part downgrade can still happen with no reason attached).

Precedence for primary_reason (highest first):
    not_reachable > conflict > quota_full > spectator > wrong_ladder > recurring > off_phase > below_bar
quota_full is only ever assigned to a row that already cleared the value bar — an event that was
never going to make it says why it's weak (below_bar, spectator, ...), not blames the quota.

verdict values: go | part | wildcard | skip | blocked | go_if | suppressed | unscored.
`unscored` added 2026-10-01 (SPEC.md §3c) — a new enum value, permitted by the §1 freeze rule
(values may be added, never redefined). Means "not enough information to judge," distinct from
`blocked` (can't even be dated) and `skip` (judged and found wanting) — see CONFIDENCE_THRESHOLD.

### Reachability is a cost, not a gate — SPEC.md, revised 2026-09-20

Superseded: `reachable == false -> reject`. An unreachable (or location-unknown) event is now
scored on value exactly like everything else; it just carries a heavy cost_blocks penalty (the
enum's max, 2.0) instead of being dropped before scoring. It can still surface, but only
conditionally: it must rank in the week's overall top 3 by predicted_p — a HIGHER bar than an
ordinary go's quota slot, not a lower one, or every previously-blocked event floods back onto the
page. Clearing that bar (and then also winning an actual slot, same as anyone else) makes it
verdict `go_if`, with `unblock_action` stating what has to be true ("GO — if you can get a ride").
Below that bar it is `suppressed` — out of the stack, but counted in `suppressed_summary` so
coverage is never silently lost. `blocked` is now reserved for rows that can't be scored or ranked
at all (no parseable start date) — reachability no longer produces it.

### conflict — redefined 2026-09-21, widened 2026-10-02

Conflict has two sources, both producing primary_reason == "conflict":
  1. Overlapping something ALREADY COMMITTED (rsvp_state == "confirmed") — Pass 5.
  2. Overlapping a higher-ranked event that took a slot the same week — Pass 3. The 2026-09-21
     version excluded this on the theory that "two recommended events overlapping each other is a
     choice for the weekly quota/ranking to resolve." In practice the ranking never resolved it:
     two events at 17:30 Tuesday both came out GO, and the `conflict` code had never appeared in
     any score_summary. A board that tells her to be in two places is worse than a wrong score —
     a wrong-but-coherent plan is still usable. So overlapping events cannot both hold a slot; the
     lower-ranked one gets `conflict` and `conflict_with` names the event it lost to. Losing to a
     conflict does not consume a quota slot, so the next-best non-overlapping candidate can take it.
"""
import datetime as dt
import json
import re
from collections import defaultdict
from pathlib import Path

from .scorer import COST_DOWNGRADES_TO_PART, GO_BAR, GO_PART_BAR

# SPEC.md §3c: below this fraction of known judgment fields, route to `unscored` instead of
# computing a tier off neutral priors. 0.5 — at least half of format/participant/target_proximity/
# cohort_saturation/prior_hook actually known — is a declared threshold, not fit to any outcome
# data; there isn't any outcome data on confidence yet to fit it to.
CONFIDENCE_THRESHOLD = 0.5

CONFIG_DIR = Path(__file__).parent.parent / "config"
WEEKLY_QUOTA_PATH = CONFIG_DIR / "weekly_quota.json"

# Phase-derived default slot budget, not frozen — "a weekly slot budget ... she sets it per week,
# derived from phase" per the 2026-09-21 request. config/weekly_quota.json overrides a specific
# week by ISO week key when she sets one by hand; this is just the fallback.
PHASE_SLOT_QUOTA = {"build": 2, "interview": 3}
CURRENT_PHASE = "build"
DEFAULT_SLOT_QUOTA = PHASE_SLOT_QUOTA.get(CURRENT_PHASE, 2)

# The quota is UNIFIED and UNCONDITIONAL, revised 2026-09-21: campus and off-campus trips compete
# for the same weekly slots, and — as of this revision — campus gets NO exemption from GO_BAR
# either. The previous version kept campus eligible regardless of value, which produced exactly
# the failure mode being fixed here: a single campus event in an otherwise-quiet week won its own
# week's slot uncontested, ~0 real value, purely because nothing else was there to rank against it
# (Story Salon: 8 separate weeks, 8 automatic "go"s). This directly contradicts SPEC.md §1's
# written allocation rule ("Campus events exist to serve S1 and S4... trips must clear the bar") —
# the doc still says campus is bar-exempt; this code now says nobody is. Not resolved quietly:
# needs her call on whether SPEC.md gets an amendment (as the reachability-as-cost change got its
# own dated section) or campus gets a real, separate carve-out restored.
GO_IF_RANK_THRESHOLD = 3  # top-3 by raw value, not just clearing GO_BAR — see module docstring
UNREACHABLE_COST_BLOCKS = 2.0  # the cost_blocks enum's max (SPEC.md §2)

RECURRING_SOON_DAYS = 21

# Multi-day listings (a weekend retreat, a "Save the Date" placeholder spanning a default 2-day
# window) don't make her unavailable for the whole span the way a single sitting does. Excluded
# from conflict entirely, on both sides of the comparison. Real data already had these (CALISADES
# 48h, Berkeley Base Camp 45h) swallow six unrelated same-week events before this exclusion.
CONFLICT_MAX_DURATION_HR = 10.0

# off_phase is wired but structurally dormant: no per-event "which phase does this serve" signal
# exists (phase transitions are an explicitly open question — SPEC.md §6, BUILD_HANDOFF.md).
PRECEDENCE = [
    "not_reachable", "conflict", "quota_full", "spectator", "wrong_ladder",
    "recurring", "off_phase", "below_bar",
]

# Sequence-suffix stripping so series detection groups "Story Salon #1" with "#2", and "Venture
# Math Speaker Series 04" with "05" (no hash — the original #\d+-only pattern missed this entirely,
# which is why `recurring` never fired on that series). Capped at 1-2 digits deliberately: a wider
# \d+ would also strip a trailing 4-digit year ("Product Club 2027") and wrongly merge unrelated
# annual events into one "series."
_SEQ_SUFFIX_RE = re.compile(r"\s*#?\d{1,2}\s*$")
_SEASON_SUFFIX_RE = re.compile(r"\s*-\s*(Fall|Spring|Summer|Winter)\s*'?\d{2,4}\s*$", re.IGNORECASE)


def _parse_dt(iso):
    if not iso:
        return None
    try:
        return dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def _pacific(d):
    return d + dt.timedelta(hours=-7)


def _iso_week(iso):
    d = _parse_dt(iso)
    return _pacific(d).isocalendar()[:2] if d else None  # (iso_year, iso_week)


def _week_key(week_tuple):
    return "{}-W{:02d}".format(*week_tuple) if week_tuple else "unscheduled"


def _series_key(row):
    """Groups same-series listings so 'next occurrence' can be computed from data we already
    have (Story Salon x8, Property & Pints x2), not from the recurring/next_occurrence schema
    fields, which nothing populates yet. Only catches series that keep a shared name template —
    see _cadence_key for the other real pattern in this data."""
    name = row.get("name") or ""
    name = _SEQ_SUFFIX_RE.sub("", name)
    name = _SEASON_SUFFIX_RE.sub("", name)
    host = (row.get("host_names") or [None])[0]
    return (row.get("source"), host, name.strip().lower())


def _cadence_key(row):
    """Second grouping path, added 2026-09-21: some series get individually RETITLED every
    occurrence and share nothing textual at all — confirmed live against CampusGroups event
    2251378, scraped 2026-09-18 as "Venture Math Speaker Series 04" and, on the same id, re-scraped
    2026-09-21 as "Speak with Nnamdi Iregbulem, Partner at Lightspeed Venture Partners" (Haas
    FinTech Club renames each session after its guest). No amount of name-suffix stripping finds
    that pair; what's stable is the host club and the weekly Wednesday 4:30pm slot itself."""
    d = _parse_dt(row.get("start"))
    club = (row.get("_raw") or {}).get("club_id")
    if not d or not club:
        return None
    local = _pacific(d)
    return (row.get("source"), club, local.weekday(), local.hour)


def _apply_recurring_groups(groups):
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda r: r["start"])
        for i in range(len(members) - 1):
            this_dt, next_dt = _parse_dt(members[i]["start"]), _parse_dt(members[i + 1]["start"])
            if this_dt and next_dt and (next_dt - this_dt).days <= RECURRING_SOON_DAYS:
                members[i]["recurring"] = True
                members[i]["next_occurrence"] = members[i + 1]["start"]
                members[i]["_raw"]["recurring_soon"] = True


def _mark_recurring(rows):
    by_name = defaultdict(list)
    by_cadence = defaultdict(list)
    for row in rows:
        if not row.get("start"):
            continue
        by_name[_series_key(row)].append(row)
        cadence_key = _cadence_key(row)
        if cadence_key:
            by_cadence[cadence_key].append(row)

    _apply_recurring_groups(by_name)
    _apply_recurring_groups(by_cadence)


def _interval(row):
    """(start, end) as datetimes. Most scraped rows have no `end` at all, so fall back to
    start + duration_hr; with neither, the interval is zero-length (and _overlaps then only
    matches an identical start). Silently treating a missing end as "ends when it starts" is
    exactly why two events at the same 17:30 both came out GO."""
    start = _parse_dt(row.get("start"))
    if start is None:
        return None, None
    end = _parse_dt(row.get("end"))
    if end is None and row.get("duration_hr"):
        end = start + dt.timedelta(hours=row["duration_hr"])
    return start, end or start


def _overlaps(a, b):
    a_start, a_end = _interval(a)
    b_start, b_end = _interval(b)
    if not (a_start and b_start):
        return False
    return a_start == b_start or (a_start < b_end and b_start < a_end)


def _can_conflict(row):
    return (row.get("duration_hr") or 0) <= CONFLICT_MAX_DURATION_HR


def _rank_key(row):
    """Order in which slot candidates are served, best first (SPEC.md §3d, option B, approved
    2026-10-02). Rank by VALUE ALONE: predicted_p is a probability and cost_blocks a block count,
    so `p - cost` silently assumed one block costs a whole unit of probability (and let a 0.42
    event beat a 0.80 one). Cost still acts, as a gate rather than a subtracted number — Pass 4
    turns a won GO into PART at cost >= COST_DOWNGRADES_TO_PART, and known-unreachable events need
    top-3 value to become go_if — and as the tiebreak here (cheaper first). A confirmed RSVP
    outranks every unconfirmed candidate: it is a commitment, not a prediction. Final tiebreaks
    (earlier start, then name) keep equal scores resolving identically on every run."""
    confirmed_first = 0 if row.get("rsvp_state") == "confirmed" else 1
    return (confirmed_first, -(row["predicted_p"] or 0.0), row["cost_blocks"],
            row.get("start") or "", row.get("name") or "")


def _load_quota_overrides():
    if WEEKLY_QUOTA_PATH.exists():
        with WEEKLY_QUOTA_PATH.open() as f:
            return json.load(f).get("overrides", {})
    return {}


def _find_carpool_candidate(row, week_members):
    """Names who could solve the ride, if anyone: a companion from another event she's already
    marked as going to, the same week. companions[] is always [] until intent-capture (step 4/5)
    starts populating it, so this has nothing to find yet on today's data — that's an honest
    empty result, not a stub."""
    for other in week_members:
        if other is row:
            continue
        for name in other.get("companions") or []:
            return name
    return None


def _unblock_action(row, week_members):
    candidate = _find_carpool_candidate(row, week_members)
    if candidate:
        return "GO — if you can get a ride. {} is going somewhere nearby that week.".format(candidate)
    return "GO — if you can get a ride."


def resolve(rows):
    """Mutates every row in place: verdict, primary_reason, reasons (+ unblock_action on go_if
    rows). Returns (skip_summary, blocked_summary, suppressed_summary, unscored_summary)."""
    _mark_recurring(rows)
    overrides = _load_quota_overrides()
    for row in rows:
        row.pop("conflict_with", None)  # recomputed below; never carry a stale "lost to" forward

    scoreable = []
    for row in rows:
        if not row.get("start"):
            # The only remaining `blocked` case now that reachability is a cost, not a gate: a
            # row with no parseable date can't be ranked into any week at all.
            row["verdict"], row["primary_reason"], row["reasons"] = "blocked", None, []
        elif (row.get("confidence") if row.get("confidence") is not None else 0.0) < CONFIDENCE_THRESHOLD:
            # SPEC.md §3c: "an event the model knows nothing about must never receive a confident
            # skip OR a confident go." Routed out before Pass 2 entirely — not ranked, not
            # competing for a quota slot, not eligible for go_if — because none of those are
            # meaningful conclusions to draw from a value computed off neutral priors. is_exploration
            # does NOT override this: "wildcard" asserts the model made a low-confidence prediction
            # and she tested it; there is no prediction to test here, only an absence of one.
            row["verdict"], row["primary_reason"], row["reasons"] = "unscored", None, []
        else:
            scoreable.append(row)

    # Pass 2: ELIGIBILITY ONLY — per the 2026-09-21 fix. Clearing GO_BAR makes an event a
    # *candidate*, nothing more; it does NOT yet grant "go". That was the actual bug: this pass
    # used to assign tier="go" directly to anything over the bar (plus an unconditional campus
    # exemption), and the quota pass only patched up the excess afterward — threshold was doing
    # both the eligibility job and the slot job. Now eligibility and slot are two different passes.
    #
    # The campus exemption is REMOVED here, not preserved: her algorithm has no carve-out for it,
    # and keeping one is exactly what let a single campus event each week win its own week
    # uncontested regardless of value (Story Salon: 8 separate weeks, 8 automatic "go"s, ~0 real
    # S2/S3 value in any of them). This is a real, visible behavior change that puts this file in
    # direct tension with SPEC.md §1's written allocation rule ("Campus events exist to serve S1
    # and S4... trips must clear the bar") — that text still says campus is exempt from the bar;
    # this code now says nobody is. Flagging this explicitly rather than quietly letting the doc
    # and the code disagree: needs her call on whether SPEC.md gets amended (matching how the
    # reachability-as-cost change got its own dated section) or campus gets its own carve-out back.
    for row in scoreable:
        reasons = []
        if row.get("participant") is False:
            reasons.append("spectator")
        if row.get("target_proximity") == "wrong_ladder":
            reasons.append("wrong_ladder")
        if row["_raw"].get("recurring_soon"):
            reasons.append("recurring")
        if row.get("phase") and row["phase"] != CURRENT_PHASE:
            reasons.append("off_phase")

        # Only a KNOWN-unreachable event (reachable is False) takes the max-cost penalty.
        # reachable is None means the location is unknown — scorer.py already priced that at the
        # neutral prior, and it competes as an ordinary candidate; treating "don't know where it
        # is" as worse than "two hours away" is the §3c error, on the cost side.
        unreachable = row.get("reachable") is False
        if unreachable:
            row["cost_blocks"] = UNREACHABLE_COST_BLOCKS
            row["_raw"]["cost_blocks_source"] = "unreachable_penalty"

        p = row["predicted_p"] or 0.0
        if unreachable:
            tier = "go_if_pending"
        elif p >= GO_BAR:
            tier = "eligible"  # a candidate for a slot — not yet a "go"
        elif p >= GO_PART_BAR:
            tier = "part"
        else:
            tier = "skip"

        if tier in ("skip", "part") and not reasons:
            reasons.append("below_bar")

        row["_tier"], row["_reasons"] = tier, reasons

    # Pass 3: per-week resolution — rank decides the slot, not the threshold.
    #   (a) go_if eligibility — pending unreachable rows must rank top-3 by raw predicted_p among
    #       EVERYONE that week to even be considered, and still clear GO_BAR outright (a weak week
    #       can't manufacture a "top 3" out of zeros).
    #   (b) the slot quota — "eligible" and "go_if" candidates are ranked by value alone, with cost
    #       as the tiebreak (SPEC.md §3d). Only the top N (that week's budget)
    #       become "go"; everyone else eligible loses to quota_full. Non-eligible rows (skip/part
    #       from Pass 2) never enter this competition at all — they already have their own reason.
    by_week = defaultdict(list)
    for r in scoreable:
        by_week[_iso_week(r.get("start"))].append(r)

    for week, members in by_week.items():
        quota = overrides.get(_week_key(week), DEFAULT_SLOT_QUOTA)

        ranked_by_value = sorted(members, key=lambda r: -(r["predicted_p"] or 0.0))
        for rank, r in enumerate(ranked_by_value, start=1):
            if r["_tier"] == "go_if_pending":
                clears_bar = (r["predicted_p"] or 0.0) >= GO_BAR
                if rank <= GO_IF_RANK_THRESHOLD and clears_bar:
                    r["_tier"] = "go_if"
                else:
                    r["_tier"] = "suppressed"
                    r["_reasons"].append("not_reachable")

        candidates = sorted(
            (r for r in members if r["_tier"] in ("eligible", "go_if")),
            key=_rank_key,
        )
        holders = []  # candidates that hold a slot, in rank order
        for r in candidates:
            # A candidate that overlaps a higher-ranked slot holder cannot also hold a slot: it
            # loses to that event by name and does NOT consume quota. Checked before the quota so
            # the reason states what it lost to, not just that the week was full.
            clash = next((h for h in holders if _can_conflict(r) and _can_conflict(h) and _overlaps(r, h)), None)
            if clash is not None:
                r["_tier"] = "skip"
                r["_reasons"].append("conflict")
                r["conflict_with"] = {"id": clash.get("id"), "name": clash.get("name"),
                                      "kind": "confirmed" if clash.get("rsvp_state") == "confirmed" else "ranked"}
            elif len(holders) < quota:
                holders.append(r)
                if r["_tier"] == "eligible":
                    r["_tier"] = "go"
                # go_if candidates that win a slot simply stay "go_if" — finalized in Pass 6.
            else:
                r["_tier"] = "skip"
                r["_reasons"].append("quota_full")

        for r in members:
            if r["_tier"] == "go_if":
                r["unblock_action"] = _unblock_action(r, members)

    # Pass 4: cost-driven go -> part downgrade (won a slot but is still expensive some other way —
    # long walk, long duration). Ranking by (value - cost_blocks) already disadvantages expensive
    # candidates in the competition itself; this catches the case where one still wins a slot
    # despite that. Deliberately does not touch go_if — that verdict already says "there's a real
    # cost here, here's the fix," so downgrading it further to "part" would be two mechanisms
    # fighting to express the same friction.
    for r in scoreable:
        if r["_tier"] == "go" and r["cost_blocks"] >= COST_DOWNGRADES_TO_PART:
            r["_tier"] = "part"

    # Pass 5: conflict against real commitments only (rsvp_state == "confirmed") — see module
    # docstring. Reads as zero today; that's correct, not broken.
    # Confirmed-vs-confirmed overlaps were already settled in Pass 3 (one holds the slot, the other
    # is marked conflict). Here a confirmed event only blocks UNCONFIRMED candidates, and only if it
    # didn't itself lose a conflict — otherwise the winner would be knocked out by the loser it just
    # beat, and the board would show neither.
    confirmed = [
        r for r in rows
        if r.get("rsvp_state") == "confirmed" and (r.get("duration_hr") or 0) <= CONFLICT_MAX_DURATION_HR
        and not r.get("conflict_with")
    ]
    for r in scoreable:
        if r.get("rsvp_state") == "confirmed":
            continue
        if r["_tier"] in ("go", "part", "go_if") and (r.get("duration_hr") or 0) <= CONFLICT_MAX_DURATION_HR:
            clash = next((c for c in confirmed if c is not r and _overlaps(r, c)), None)
            if clash is not None:
                r["_tier"] = "skip"
                r["_reasons"].append("conflict")
                r["conflict_with"] = {"id": clash.get("id"), "name": clash.get("name"), "kind": "confirmed"}

    # Pass 6: finalize. wildcard overrides tier but keeps the underlying reasons — SPEC.md §3's
    # exploration mechanism needs to know what the model would have skipped it for.
    for r in scoreable:
        tier, reasons = r.pop("_tier"), r.pop("_reasons")
        verdict = "wildcard" if r.get("is_exploration") else tier

        if verdict == "go":
            r["verdict"], r["primary_reason"], r["reasons"] = "go", None, []
        elif verdict == "go_if":
            r["verdict"] = "go_if"
            r["reasons"] = reasons if reasons else ["not_reachable"]
            r["primary_reason"] = next((c for c in PRECEDENCE if c in r["reasons"]), "not_reachable")
        else:
            r["verdict"] = verdict
            r["reasons"] = reasons
            r["primary_reason"] = next((c for c in PRECEDENCE if c in reasons), None)

    def summarize(subset):
        by_reason = {}
        for r in subset:
            by_reason[r["primary_reason"]] = by_reason.get(r["primary_reason"], 0) + 1
        return {"total": len(subset), "by_reason": by_reason}

    skip_summary = summarize([r for r in rows if r["verdict"] == "skip"])
    blocked_summary = summarize([r for r in rows if r["verdict"] == "blocked"])
    suppressed_summary = summarize([r for r in rows if r["verdict"] == "suppressed"])
    unscored_summary = summarize([r for r in rows if r["verdict"] == "unscored"])
    return skip_summary, blocked_summary, suppressed_summary, unscored_summary
