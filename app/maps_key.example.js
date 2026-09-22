/*
 * Copy this file to app/maps_key.local.js (already gitignored — see .gitignore) and set your
 * own Google Maps JavaScript API key below. Get one from Google Cloud Console:
 *   1. console.cloud.google.com → a project with billing enabled.
 *   2. Enable the "Maps JavaScript API".
 *   3. Create an API key, then restrict it: "HTTP referrers" → add the origin(s) you'll open
 *      this page from (e.g. http://localhost:4173/* for local preview, and/or the exact
 *      file path if opening via file://). Also restrict it to just the Maps JavaScript API.
 *
 * A Maps JS API key is meant to be visible in client-side code — the referrer restriction is
 * what actually protects it, not secrecy. Still: keep app/maps_key.local.js out of git (it
 * already is) so you don't have to reconfigure the restriction every time it leaks into a
 * public repo by accident.
 *
 * If this file is absent, the board falls back to a schematic (non-Google) map automatically —
 * see DESIGN_BRIEF.md's "no server, opens anywhere" requirement, which a live Google Maps
 * dependency can't fully satisfy on its own.
 */
window.GOOGLE_MAPS_API_KEY = "";
