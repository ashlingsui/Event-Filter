/*
 * Want/Pass + context-strip answers, saved to this browser only (localStorage) — there is no
 * server, and a static page can't write to data/*.json. This is NOT the real capture layer
 * (capture/ + data/outcomes.json); it's a per-device stand-in until that's built. Every read of
 * this data in the UI must say so plainly rather than imply it's part of the outcome record.
 */
const IntentStore = (() => {
  const KEY_PREFIX = "skipgo:intent:v1:";

  function get(eventId) {
    try {
      const raw = localStorage.getItem(KEY_PREFIX + eventId);
      return raw ? JSON.parse(raw) : null;
    } catch (err) {
      return null; // private browsing, storage disabled, or quota exceeded — degrade to "no saved answer"
    }
  }

  function set(eventId, data) {
    try {
      localStorage.setItem(KEY_PREFIX + eventId, JSON.stringify({ ...data, saved_at: new Date().toISOString() }));
      return true;
    } catch (err) {
      return false;
    }
  }

  function clear(eventId) {
    try {
      localStorage.removeItem(KEY_PREFIX + eventId);
    } catch (err) {
      // nothing to do — if we couldn't write, there's nothing stored to remove either
    }
  }

  return { get, set, clear };
})();
