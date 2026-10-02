"""Step 3: Score. SPEC.md §3 locks the order of operations and nothing else: "Hard filters run
first (reachable == false → reject), then a weighted combination minus cost_blocks, with
multipliers for prior_hook, companions, trip_chained, cohort_saturation." The formula, weights,
and thresholds below are explicitly NOT frozen — this is a hand-specified v0 heuristic, small and
interpretable on purpose (LESSONS.md #13: at 2-4 events/week, a fitted model is theater; a model
you can read a line of and know why it said what it said is not). Replace with fitted weights once
there's enough pooled multi-user data for that to mean something (SPEC.md §3, multi-user).

Two design commitments carried over from LESSONS.md, both violated easily if you're not careful:

  #5 "Keep value and cost in separate columns." predicted_p is pure value/probability — cost never
  enters it. cost_blocks is a separate axis that gates the go/skip/go-for-part decision. Folding
  cost into predicted_p is exactly the mistake that corrupts both numbers.

  §1 allocation rule: "Campus events exist to serve S1/S4. Trips out of Berkeley must clear the bar
  on S2 or S3." This is encoded directly, not left to a single global threshold — an on-campus
  event basically always clears (it's not spending a trip), an off-campus trip has to earn it.
"""
import datetime as dt

# --- S3 (build) potential by format. Gated by `participant`: per SPEC.md §2, participant asks
# "can I legitimately DO the thing this event is for" — a format's build-potential is moot if she
# can't actually take part (e.g. she isn't eligible to build/exhibit at it).
FORMAT_S3_POINTS = {
    "build_night": 2.0,
    "hackathon": 2.0,
    "demo_day": 1.5,
    "workshop": 1.0,
    "panel": 0.0,
    "fireside": 0.0,
    "mixer": 0.0,
    "lecture": 0.0,
    "class": 0.0,
    # Added 2026-10-01 for Tier 1 rule-based classification (enrich/rules.py) — 1:1 or small-group
    # Q&A, not hands-on building, same build-potential tier as the other spectator-adjacent
    # formats until there's evidence to weight it differently.
    "office_hours": 0.0,
}

# --- S2 (contact) potential by room composition. wrong_ladder scores the same as none (no target-
# company density either way) but is kept distinct in the `why` string — it's diagnostic
# information ("VC/founder room, not an employer room"), not just an absence of signal.
TARGET_PROXIMITY_POINTS = {
    "none": 0.0,
    "wrong_ladder": 0.0,
    "some": 1.0,
    "high": 2.0,
}

# --- SPEC.md §3c "Unknown is not zero". `.get(key, 0.0)` used to make an unknown format or an
# unknown participant score identically to a confidently bad one — a null read as absence of
# value, not absence of information. These are declared constants, NOT derived from the 21
# currently-enriched rows (that sample is hand-picked and biased upward; fitting a prior to it
# would bake the bias in). Each is the midpoint of its dimension's possible range — maximum
# uncertainty, not an educated guess at the true distribution. Replace with a real base rate once
# there's an unbiased sample to compute one from.
NEUTRAL_PRIOR_S3 = 1.0  # midpoint of FORMAT_S3_POINTS' range [0.0, 2.0]
NEUTRAL_PRIOR_S2 = 1.0  # midpoint of TARGET_PROXIMITY_POINTS' range [0.0, 2.0]
# Unknown participant: neither "she can do the thing" (1.0) nor "she can't" (0.0) — halves
# whatever format points apply, same midpoint-of-range logic as the two priors above.
NEUTRAL_PARTICIPANT_MULT = 0.5

# Scoring-relevant judgment fields — confidence (SPEC.md §3c) is the fraction of these actually
# known on a given row, not a proxy for data completeness in general (host_tier, speakers, etc.
# are recorded but don't drive the value formula, so they don't belong in this denominator).
CONFIDENCE_FIELDS = ("format", "participant", "target_proximity", "cohort_saturation", "prior_hook")


def confidence(row):
    known = sum(1 for f in CONFIDENCE_FIELDS if row.get(f) is not None)
    return round(known / len(CONFIDENCE_FIELDS), 2)


# --- Multipliers. All positive-only except cohort_saturation and size, per BUILD_HANDOFF.md:
# "Never frame going to events with friends as a cost. Companions are a positive." prior_hook
# boost matches LESSONS.md #12 ("a prior hook is what makes the room warm"). cohort_saturation
# penalty matches LESSONS.md #9 (a saturated room, not companionship, is what kills new-contact
# yield).
PRIOR_HOOK_MULT = {"none": 1.0, "topic": 1.2}
COHORT_SATURATION_MULT = {"none": 1.0, "some": 0.85, "high": 0.6}
COMPANIONS_MULT = 1.15

# size (guest_count) enters the value model — added 2026-09-21. Her clearest labeled contrast so
# far: the 200-person Founder & Funder Night delivered nothing; the small a16z build night was the
# one confirmed hit. Buckets are drawn from the real distribution in the current data (checked live
# 2026-09-21: 76 of 104 sized rows read exactly 0), not picked blind. 0 is deliberately treated as
# "no signal yet", same as None — Luma's guest_count is a live RSVP count, so a just-listed event
# reads 0 for reasons that have nothing to do with room size, and would otherwise get wrongly
# boosted as "intimate." This makes the signal noisiest for events far from their date and most
# reliable close to it, which is an honest property of the data, not a flaw to paper over.
def _size_mult(size):
    if not size:
        return 1.0
    if size <= 20:
        return 1.15
    if size <= 75:
        return 1.0
    if size <= 150:
        return 0.85
    return 0.65


# raw value tops out around 4 * 1.2 * 1.15 * 1.15 ≈ 6.3 (S3 max 2 + S2 max 2, full hook + companion
# + small-room boost, no cohort penalty) — divisor chosen so a near-ceiling event lands under the
# 0.95 cap rather than blowing through it into false certainty; predicted_p is clamped regardless.
VALUE_TO_P_DIVISOR = 6.0
MAX_PREDICTED_P = 0.95

# Off-campus trips must clear a real bar (SPEC.md §1); campus events don't need to, since they're
# not spending a trip. go-for-part-only exists for the case where an event clears the value bar
# but is also expensive enough that the smart move is to catch the valuable part and leave.
GO_BAR = 0.30
GO_PART_BAR = 0.15
COST_DOWNGRADES_TO_PART = 1.5

# cost_blocks estimate, used only when the row doesn't already carry a manually-set value (never
# overwrites one — this is a fallback, not an authority). Grid matches SPEC.md §2's enum.
# Uncapped final bucket matters more than it used to: score_row now runs for every row regardless
# of reachability (see below), including international noise events whose bart_walk_min can run
# into the hundreds of thousands of minutes — without a catch-all this raised StopIteration the
# moment the old reachable-only early return was removed.
WALK_COST_BREAKS = [(10, 0.0), (20, 0.5), (99, 1.0), (float("inf"), 2.0)]
FRIDAY_DISCOUNT = 0.5  # BUILD_HANDOFF.md: "No class Fridays. Friday events cost almost nothing."
TRIP_CHAINED_DISCOUNT = 1.0  # LESSONS.md #5: the Yosemite/OpenRouter case — cost went to ~zero
LONG_EVENT_SURCHARGE_HR = 4.0
LONG_EVENT_SURCHARGE = 0.5


def _pacific_weekday(start_iso):
    """Best-effort local weekday from a UTC ISO timestamp. Uses a fixed seasonal PDT/PST offset
    rather than a tz database (not available in this environment's default Python) — wrong only
    for events within a week of a DST transition, which is an acceptable approximation for a
    Friday-discount heuristic, not for anything outcome-bearing."""
    if not start_iso:
        return None
    try:
        clean = start_iso.replace("Z", "+00:00")
        utc_dt = dt.datetime.fromisoformat(clean)
    except ValueError:
        return None
    offset_hours = -7 if 3 <= utc_dt.month <= 10 else -8
    local_dt = utc_dt + dt.timedelta(hours=offset_hours)
    return local_dt.weekday()  # Monday=0 ... Friday=4, Sunday=6


def _estimate_cost_blocks(row):
    walk = row.get("bart_walk_min")
    cost = next(pts for cutoff, pts in WALK_COST_BREAKS if (walk or 0) <= cutoff)

    if _pacific_weekday(row.get("start")) == 4:
        cost = max(0.0, cost - FRIDAY_DISCOUNT)
    if row.get("trip_chained"):
        cost = max(0.0, cost - TRIP_CHAINED_DISCOUNT)
    if (row.get("duration_hr") or 0) > LONG_EVENT_SURCHARGE_HR:
        cost += LONG_EVENT_SURCHARGE

    return round(round(min(2.0, cost) * 2) / 2, 2)  # snap to the 0.5 grid, clamp to [0, 2]


def _is_campus(row):
    return row.get("source") == "campusgroups" or (row.get("city") or "").strip().lower() == "berkeley"


def score_row(row):
    """Mutates row in place: sets predicted_p, cost_blocks (only if unset), and a factor-breakdown
    _raw.why. This function owns the value/cost MODEL only — it does not decide go/skip/part, and
    as of 2026-09-20 it does not know about reachability at all: "reachability is a cost, not a
    gate" (SPEC.md) moved that entirely into verdicts.py, which penalizes cost_blocks after this
    runs. Earlier this function still short-circuited to predicted_p=0.0/None for anything not
    confirmed reachable — a leftover hard gate that silently zeroed the value of every unreachable
    event regardless of its actual classification, which meant nothing could ever have been good
    enough to surface as `go_if`. Fixed: value is computed the same way regardless of reachability."""
    why = []

    # SPEC.md §3c: null is not 0. A format/participant/target_proximity we never looked at scores
    # at its NEUTRAL_PRIOR, not at the floor — see the constants above for why these particular
    # numbers and not a fitted one.
    if row.get("format") is not None:
        format_points = FORMAT_S3_POINTS.get(row["format"], 0.0)
    else:
        format_points = NEUTRAL_PRIOR_S3
        why.append("format unknown -> neutral prior {:.1f}".format(NEUTRAL_PRIOR_S3))

    if row.get("participant") is not None:
        participant_mult = 1.0 if row["participant"] else 0.0
    else:
        participant_mult = NEUTRAL_PARTICIPANT_MULT
        why.append("participant unknown -> neutral prior ×{:.2f}".format(NEUTRAL_PARTICIPANT_MULT))

    s3 = format_points * participant_mult

    if row.get("target_proximity") is not None:
        s2 = TARGET_PROXIMITY_POINTS.get(row["target_proximity"], 0.0)
    else:
        s2 = NEUTRAL_PRIOR_S2
        why.append("target_proximity unknown -> neutral prior {:.1f}".format(NEUTRAL_PRIOR_S2))

    why.append("S3(format={},participant={})={:.2f}".format(row.get("format"), row.get("participant"), s3))
    why.append("S2(target_proximity={})={:.2f}".format(row.get("target_proximity"), s2))

    hook_mult = PRIOR_HOOK_MULT.get(row.get("prior_hook"), 1.0)
    cohort_mult = COHORT_SATURATION_MULT.get(row.get("cohort_saturation"), 1.0)
    companion_mult = COMPANIONS_MULT if row.get("companions") else 1.0
    size_mult = _size_mult(row.get("size"))
    if hook_mult != 1.0:
        why.append("×{:.2f} prior_hook={}".format(hook_mult, row["prior_hook"]))
    if cohort_mult != 1.0:
        why.append("×{:.2f} cohort_saturation={}".format(cohort_mult, row["cohort_saturation"]))
    if companion_mult != 1.0:
        why.append("×{:.2f} companions".format(companion_mult))
    if size_mult != 1.0:
        why.append("×{:.2f} size={}".format(size_mult, row.get("size")))
    if row.get("target_proximity") == "wrong_ladder":
        why.append("wrong_ladder: VC/founder room, not a target-employer room")

    value = (s3 + s2) * hook_mult * cohort_mult * companion_mult * size_mult
    predicted_p = round(min(MAX_PREDICTED_P, value / VALUE_TO_P_DIVISOR), 2)
    row["predicted_p"] = predicted_p
    row["confidence"] = confidence(row)

    if row.get("cost_blocks") is None:
        row["cost_blocks"] = _estimate_cost_blocks(row)
        row["_raw"]["cost_blocks_source"] = "estimated"
    else:
        row["_raw"]["cost_blocks_source"] = "manual"

    row["_raw"]["why"] = " | ".join(why)
    return row


def score_all(rows):
    for row in rows:
        score_row(row)
    return rows
