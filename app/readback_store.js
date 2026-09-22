/*
 * Free-text read-back notes, saved to this browser only. SPEC.md §1c: "Free text is capture
 * input. Do not turn it directly into a recorded fact without a reviewable step" — and there is
 * no live extraction here at all (see app/app.js's readback section for why: real extraction
 * needs an LLM call, which needs a server-held API key; a static page has neither, and unlike
 * the Google Maps key, an Anthropic key is a real secret that must never sit in client-side
 * code). So a note saved here stays exactly what she typed — appended to this event's list,
 * timestamped, never auto-converted into a Recorded fact or a Suspected hypothesis. Turning it
 * into either is a real, separate, reviewable step (capture_feedback.py, run by hand).
 */
const ReadbackStore = (() => {
  const KEY_PREFIX = "skipgo:readback:v1:";

  function getNotes(eventId) {
    try {
      const raw = localStorage.getItem(KEY_PREFIX + eventId);
      return raw ? JSON.parse(raw) : [];
    } catch (err) {
      return [];
    }
  }

  function addNote(eventId, text) {
    const notes = getNotes(eventId);
    notes.push({ text, saved_at: new Date().toISOString() });
    try {
      localStorage.setItem(KEY_PREFIX + eventId, JSON.stringify(notes));
      return true;
    } catch (err) {
      return false;
    }
  }

  return { getNotes, addNote };
})();
