/*
 * The single data-access module. Every view reads events, weeks, and summaries through
 * DataAccess — nothing else touches window.EVENT_FILTER_DATA directly. Swapping the local
 * JSON snapshot for a live Supabase/API backend later means rewriting the bodies of the
 * functions below (and how EVENT_FILTER_DATA gets populated); no view code should need to
 * change. Loaded as a plain script (not a module) so the app still opens over file:// with
 * no server.
 */
const DataAccess = (() => {
  function raw() {
    if (!window.EVENT_FILTER_DATA) {
      throw new Error("EVENT_FILTER_DATA missing — run `python3 app/build_data.py` and reload.");
    }
    return window.EVENT_FILTER_DATA;
  }

  function getEvents() {
    return raw().events;
  }

  function getEvent(id) {
    return raw().events.find((e) => e.id === id) || null;
  }

  function getEventsForWeek(weekKey) {
    return raw().events.filter((e) => e.week_key === weekKey);
  }

  function getWeeks() {
    return raw().weeks;
  }

  function getScoreSummary() {
    return raw().score_summary;
  }

  // Outcomes and pending hypotheses contain named real people (SPEC.md §4 privacy boundary) and
  // live in a SEPARATE, gitignored generated file (app/generated/private_data.js) — never in
  // EVENT_FILTER_DATA, which is committed. That file only exists after a local
  // `python3 app/build_data.py` run; a fresh clone or a page shared with someone else won't have
  // it, so these return null rather than throwing.
  function getOutcomes() {
    const p = window.EVENT_FILTER_PRIVATE_DATA;
    return p ? p.outcomes : null;
  }

  function getPendingHypotheses() {
    const p = window.EVENT_FILTER_PRIVATE_DATA;
    return p ? p.pending_hypotheses : null;
  }

  function getGeneratedAt() {
    return raw().generated_at;
  }

  function getSourceScoredAt() {
    return raw().source_scored_at;
  }

  // The week key the board should default to, derived in app/build_data.py from the pipeline's
  // own scored_at timestamp — not a hardcoded constant that goes stale after the next run.
  function getCurrentWeekKey() {
    return raw().current_week_key;
  }

  function getSocialCohortNote() {
    return raw().social_cohort_overrides_note;
  }

  function getMapBounds() {
    return raw().map_bounds;
  }

  function getMapReferenceCities() {
    return raw().map_reference_cities;
  }

  // California-only count, recomputed after excluding out-of-state/international rows
  // entirely (Ashling's call, 2026-09-21) — not the raw score_summary.json total, which still
  // includes them. getExcludedNonCaliforniaCount() exists for later use; nothing renders it today.
  function getCaliforniaSuppressedTotal() {
    return raw().ca_suppressed_total;
  }

  function getExcludedNonCaliforniaCount() {
    return raw().excluded_non_california_count;
  }

  return {
    getEvents,
    getEvent,
    getEventsForWeek,
    getWeeks,
    getScoreSummary,
    getOutcomes,
    getPendingHypotheses,
    getGeneratedAt,
    getSourceScoredAt,
    getCurrentWeekKey,
    getSocialCohortNote,
    getMapBounds,
    getMapReferenceCities,
    getCaliforniaSuppressedTotal,
    getExcludedNonCaliforniaCount,
  };
})();
