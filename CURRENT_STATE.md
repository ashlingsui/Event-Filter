# Current state

Updated: 2026-10-02

**2026-10-02 pass (supersedes the stale frontend notes below — all v12 routes are built):**
- One command refreshes everything: `scripts/refresh.sh` (ingest -> enrich -> score ->
  `app/build_data.py` -> final counts). `scripts/check.sh` now also runs `scripts/selftest.py` and a
  drift check that regenerates `app/generated/data.js` and fails if it differs from what is on disk.
- Hand-entered values are protected: rows carry `_manual: {fields, ...}`; `manual_guard.py` makes
  ingest/enrich/score restore those fields after each stage and record what the stage wanted in
  `_manual.shadow`. Each run prints (and `score_summary.json` stores) how many overwrites were blocked.
- `prior_hook` `person` is now scored (x1.3, above `topic` x1.2); `score/scorer.py` refuses to load if
  any SPEC.md §2 enum value lacks a table entry, and rejects an unrecognized value instead of
  defaulting. Overlapping events can no longer both hold a slot (`conflict`, with `conflict_with`).
- Unknown location is a neutral cost prior (1.0 block) with lower confidence, not the worst case;
  `cost_blocks` is recomputed every run unless listed in `_manual.fields`.
- `enrich/rules.py` (tier 1, no model) also fills `participant` and `target_proximity`
  (employer list: `config/target_employers.json`).
- The page shows data age and a loud banner past 48h (`data/ingest_meta.json` records the scrape time).
- OPEN, awaiting a decision: SPEC.md §3d proposes replacing the `predicted_p - cost_blocks` slot ranking
  (mixed units). Not implemented.
- Not deployed: the site is local-only; `vercel.json` exists but no Vercel project is linked.

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
  (`app/intent_store.js`, localStorage — explicitly not the real `capture/` layer). Step 3
  (read-back, `#/readback`, reachable from the rail nav — real hash routing now exists between
  views) is built too: choose an attended event from `data/outcomes.json`, its real Recorded
  facts and the Suspected hypotheses that name it as supporting evidence
  (`data/pending_hypotheses.json`) display side by side, and free text saves as a note
  (`app/readback_store.js`, localStorage) rather than being auto-extracted — there is no live
  LLM extraction anywhere in this build; that needs a server-held API key, which a static page
  can't safely hold (SPEC.md §5). Step 4 (prep/learn/about/intake) is not built yet.
  Two conflicts were surfaced and resolved with Ashling before building: `quota_full` renders
  as "lost its slot to `<event>`", never a capacity meter; the SPEC/brief principle lines stay
  as the board headline + Learning/About material, and the handoff's four decision-tier lines
  are reserved for the event-detail decision banner (step 2, not built yet). A third issue came
  up during grounding: the board's Social/Cohort lane has no real pipeline field to key off of
  (`score/verdicts.py` doesn't classify by track, and a per-club rule doesn't work — see
  `docs/ARCHITECTURE.md`). Resolved for now via `app/config/social_cohort_overrides.json`, a
  small manual allowlist with Claude's draft guesses that Ashling has not yet reviewed.
