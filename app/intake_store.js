/*
 * Candidates created on #/intake by pasting a link. DESIGN_V12_HANDOFF.md §5: pasting a URL
 * creates an UNSCORED candidate, never a scored event. There is no server for a static page to
 * fetch an arbitrary URL or run ingest/enrich/score against it, so this stores only the URL and a
 * derived label — saved to this browser only, always labeled UNSCORED. It can never become a real
 * row in data/events.json from here; that needs an actual `python3 run_ingest.py` /
 * `python3 score_events.py` run (or SPEC.md §5's serverless fix) to pick the URL up for real.
 */
const IntakeStore = (() => {
  const KEY = "skipgo:intake:v1";

  function getAll() {
    try {
      const raw = localStorage.getItem(KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (err) {
      return [];
    }
  }

  function save(all) {
    try {
      localStorage.setItem(KEY, JSON.stringify(all));
      return true;
    } catch (err) {
      return false;
    }
  }

  function add({ name, url, source_label }) {
    const all = getAll();
    const row = {
      event_id: `intake:${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
      name: name || url,
      url: url || null,
      source_label: source_label || "Unknown platform",
      status: "unscored",
      created_at: new Date().toISOString(),
    };
    all.push(row);
    save(all);
    return row;
  }

  return { getAll, add };
})();
