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

  // PLANS vs. METHOD split (SPEC.md §4, app/build_data.py's event_private comment): intent,
  // rsvp_state, is_exploration, and companions (which can carry OTHER PEOPLE'S NAMES) never ship
  // in the committed app/generated/data.js. When private_data.js is present (local use), this
  // joins them back onto the event transparently, so every existing call site keeps working
  // unchanged. When it's absent (public deploy), the merge is a no-op and those four keys are
  // simply missing — every current reader already falls back safely on undefined (`e.companions
  // && ...`, `e.rsvp_state || "none"`, `!!(e && e.is_exploration)`), so this degrades to showing
  // verdicts/reasoning with no want/pass or companion context, never a crash or blank screen.
  function _withPrivateFields(event) {
    const p = window.EVENT_FILTER_PRIVATE_DATA;
    const extra = p && p.event_private && p.event_private[event.id];
    return extra ? { ...event, ...extra } : event;
  }

  function getEvents() {
    return raw().events.map(_withPrivateFields);
  }

  function getEvent(id) {
    const e = raw().events.find((e) => e.id === id);
    return e ? _withPrivateFields(e) : null;
  }

  function getEventsForWeek(weekKey) {
    return raw().events.filter((e) => e.week_key === weekKey).map(_withPrivateFields);
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

  // The three moments that decide how old the board really is: when the scrape ran, when scoring
  // ran, and when this file was built. Any may be null (ingest_meta.json only exists once ingest
  // has run since it was added).
  function getDataTimes() {
    const d = raw();
    return { ingested: d.source_ingested_at || null, scored: d.source_scored_at || null, built: d.generated_at || null };
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

  // California-only count — not the raw score_summary.json total, which predates ingest's region
  // filter and still includes rows that never reach data/events.json anymore.
  function getCaliforniaSuppressedTotal() {
    return raw().ca_suppressed_total;
  }

  // Should always be 0 — see app/build_data.py's verification-pass comment. Non-zero means
  // ingest's region filter (ingest/region.py) let an out-of-region row through; nothing renders
  // this in the UI today, it exists for that diagnosis.
  function getOutOfRegionCount() {
    return raw().out_of_region_count;
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
    getDataTimes,
    getSourceScoredAt,
    getCurrentWeekKey,
    getSocialCohortNote,
    getMapBounds,
    getMapReferenceCities,
    getCaliforniaSuppressedTotal,
    getOutOfRegionCount,
  };
})();
