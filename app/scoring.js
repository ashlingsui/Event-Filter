/*
 * A faithful client-side port of score/scorer.py's VALUE formula only — not score/verdicts.py's
 * weekly ranking/quota logic, which depends on every other candidate that week and isn't safe
 * to reproduce from a single event's data in the browser. This lets the event-detail context
 * strip (ride/companion/warm-hook) recompute a real P live; the go/part/skip VERDICT itself
 * stays authoritative from the next actual pipeline run, and the UI says so explicitly rather
 * than implying this recomputes the decision.
 *
 * Every constant below is copied from score/scorer.py — if that file's formula changes, this
 * one needs to change with it. There is no automated check that they stay in sync; a human has
 * to notice. That's a real, known gap (see docs/ARCHITECTURE.md).
 */
const Scoring = (() => {
  const FORMAT_S3_POINTS = {
    build_night: 2.0, hackathon: 2.0, demo_day: 1.5, workshop: 1.0,
    panel: 0.0, fireside: 0.0, mixer: 0.0, lecture: 0.0, class: 0.0,
  };
  const TARGET_PROXIMITY_POINTS = { none: 0.0, wrong_ladder: 0.0, some: 1.0, high: 2.0 };
  const PRIOR_HOOK_MULT = { none: 1.0, topic: 1.2 };
  const COHORT_SATURATION_MULT = { none: 1.0, some: 0.85, high: 0.6 };
  const COMPANIONS_MULT = 1.15;
  const VALUE_TO_P_DIVISOR = 6.0;
  const MAX_PREDICTED_P = 0.95;
  const WALK_COST_BREAKS = [[10, 0.0], [20, 0.5], [99, 1.0], [Infinity, 2.0]];
  const FRIDAY_DISCOUNT = 0.5;
  const TRIP_CHAINED_DISCOUNT = 1.0;
  const LONG_EVENT_SURCHARGE_HR = 4.0;
  const LONG_EVENT_SURCHARGE = 0.5;
  const UNREACHABLE_COST_BLOCKS = 2.0;

  function sizeMult(size) {
    if (!size) return 1.0;
    if (size <= 20) return 1.15;
    if (size <= 75) return 1.0;
    if (size <= 150) return 0.85;
    return 0.65;
  }

  // context: { ride: bool|null, companion: bool|null, hook: bool|null } — null/undefined means
  // "no answer given," in which case the event's own scraped field is used unchanged.
  function recomputeP(event, context) {
    const participant = event.participant;
    const s3 = participant ? (FORMAT_S3_POINTS[event.format] ?? 0.0) : 0.0;
    const s2 = TARGET_PROXIMITY_POINTS[event.target_proximity] ?? 0.0;

    const priorHook = context.hook === true ? "topic" : (event.prior_hook || "none");
    const hookMult = PRIOR_HOOK_MULT[priorHook] ?? 1.0;

    const cohortMult = COHORT_SATURATION_MULT[event.cohort_saturation] ?? 1.0;

    const hasCompanion = context.companion === true || (event.companions && event.companions.length > 0);
    const companionMult = hasCompanion ? COMPANIONS_MULT : 1.0;

    const szMult = sizeMult(event.size);

    const value = (s3 + s2) * hookMult * cohortMult * companionMult * szMult;
    return Math.min(MAX_PREDICTED_P, Math.round((value / VALUE_TO_P_DIVISOR) * 100) / 100);
  }

  function pacificWeekday(startIso) {
    // Python's dt.weekday(): Monday=0 ... Sunday=6. JS getUTCDay(): Sunday=0 ... Saturday=6.
    if (!startIso) return null;
    const d = new Date(startIso);
    if (Number.isNaN(d.getTime())) return null;
    const month = d.getUTCMonth() + 1;
    const offsetHours = month >= 3 && month <= 10 ? -7 : -8; // same seasonal PDT/PST approximation as scorer.py
    const local = new Date(d.getTime() + offsetHours * 3600 * 1000);
    return (local.getUTCDay() + 6) % 7;
  }

  function walkCost(bartWalkMin) {
    const m = bartWalkMin || 0;
    for (const [cutoff, pts] of WALK_COST_BREAKS) {
      if (m <= cutoff) return pts;
    }
    return 2.0;
  }

  // context.ride answers SPEC.md §1b's "have a ride?" — mapped to trip_chained (the field it's
  // documented against), and also replaces the flat UNREACHABLE_COST_BLOCKS penalty with the
  // ordinary walk-tier estimate when the event was scored unreachable, since a ride is exactly
  // what verdicts.py's go_if mechanism says would solve that ("GO — if you can get a ride").
  function recomputeCostBlocks(event, context) {
    const rideAnswered = context.ride === true;
    const wasUnreachablePenalty = event.reachable === false;
    let cost = wasUnreachablePenalty && rideAnswered
      ? walkCost(event.bart_walk_min)
      : (typeof event.cost_blocks === "number" ? event.cost_blocks : walkCost(event.bart_walk_min));

    if (pacificWeekday(event.start) === 4) cost = Math.max(0, cost - FRIDAY_DISCOUNT);
    if (rideAnswered || event.trip_chained) cost = Math.max(0, cost - TRIP_CHAINED_DISCOUNT);
    if ((event.duration_hr || 0) > LONG_EVENT_SURCHARGE_HR) cost += LONG_EVENT_SURCHARGE;

    cost = Math.min(2.0, Math.max(0, cost));
    return Math.round(cost * 2) / 2; // snap to the 0.5 grid, same as scorer.py
  }

  return { recomputeP, recomputeCostBlocks, UNREACHABLE_COST_BLOCKS };
})();
