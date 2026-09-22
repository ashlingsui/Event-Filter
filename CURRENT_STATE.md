# Current state

Updated: 2026-09-21

- Current frontend UX reference: `design_v12.html`. Implementation contract for the
  next code/data iteration: `DESIGN_V12_HANDOFF.md` (2026-09-21).
- Git was initialized for the existing Event Filter workspace; there was no prior repository
  history.
- The shared handoff contract is `AGENTS.md`; `CLAUDE.md` imports it.
- The local pipeline is present through ingest, enrichment, scoring/verdicts, and outcome
  capture. Static HTML prototypes are also present. Supabase support exists as source code and
  SQL only; no Supabase operation was run during this foundation pass.
- `supabase/.env` is ignored. Its `SUPABASE_SERVICE_ROLE_KEY` entry is malformed (value
  withheld) and requires explicit user-approved correction. No credentials were changed or
  exposed.
- `supabase/apply_schema.py` now requires a fully verifying TLS configuration and the
  published Supabase CA certificate. It still must not be run without explicit user
  authorization, valid credentials, and the required local certificate.
- Shared local verification: `scripts/check.sh`.
- Frontend build started 2026-09-21, against `design_v12.html`/`DESIGN_V12_HANDOFF.md`, one
  route at a time per that handoff's sequence, stopping for review after each. Step 1 (decision
  board, `#/choose`) is built in `app/`, grounded in real `data/events.json` /
  `data/score_summary.json` via `app/build_data.py` + `app/data_access.js` — no fixture data.
  Step 2 (event detail overlay, opened from the board's "OPEN DETAILS" action) is now built
  too: decision banner with the handoff's four principle lines, Want/Pass + the ride/companion/
  warm-hook context strip with a live P recompute (`app/scoring.js`, a faithful port of
  `score/scorer.py`'s value formula — the verdict itself stays authoritative from the next real
  pipeline run), why-grid/facts/provenance from real fields, and per-device intent persistence
  (`app/intent_store.js`, localStorage — explicitly not the real `capture/` layer). Steps 3–4
  (read-back, then prep/learn/about/intake) are not built yet.
  Two conflicts were surfaced and resolved with Ashling before building: `quota_full` renders
  as "lost its slot to `<event>`", never a capacity meter; the SPEC/brief principle lines stay
  as the board headline + Learning/About material, and the handoff's four decision-tier lines
  are reserved for the event-detail decision banner (step 2, not built yet). A third issue came
  up during grounding: the board's Social/Cohort lane has no real pipeline field to key off of
  (`score/verdicts.py` doesn't classify by track, and a per-club rule doesn't work — see
  `docs/ARCHITECTURE.md`). Resolved for now via `app/config/social_cohort_overrides.json`, a
  small manual allowlist with Claude's draft guesses that Ashling has not yet reviewed.
