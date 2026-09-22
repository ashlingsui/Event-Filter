/*
 * Events you attended that the local pipeline never scored — a link you paste in, not something
 * that came off a followed calendar. There is no server here, so these can never become real
 * rows in data/outcomes.json; they live entirely in this browser's localStorage, clearly
 * separate from the real pipeline record (app/app.js always labels them "Added by you").
 *
 * Capture is intentionally narrow: SPEC.md §1's T+0/T+1 capture point is felt_score (0-10) + one
 * free-text line, nothing else. s1-s4/hit require the T+7 recognition method (show her the
 * scraped names, ask "any of these?") — that has no meaning for an event this page never scraped
 * anything about, so this store doesn't pretend to collect it.
 */
const LocalOutcomeStore = (() => {
  const KEY = "skipgo:local_outcomes:v1";

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

  function add({ name, url, date }) {
    const all = getAll();
    const row = {
      event_id: `local:${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`,
      name: name || url,
      url: url || null,
      date: date || new Date().toISOString().slice(0, 10),
      local: true,
      created_at: new Date().toISOString(),
      felt_score: null,
      felt_note: null,
    };
    all.push(row);
    save(all);
    return row;
  }

  function setFeeling(eventId, { felt_score, felt_note }) {
    const all = getAll();
    const row = all.find((r) => r.event_id === eventId);
    if (!row) return null;
    if (felt_score !== undefined) row.felt_score = felt_score;
    if (felt_note !== undefined) row.felt_note = felt_note;
    save(all);
    return row;
  }

  return { getAll, add, setFeeling };
})();
