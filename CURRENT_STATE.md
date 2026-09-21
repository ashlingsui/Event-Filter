# Current state

Updated: 2026-09-21

- Git was initialized for the existing Event Filter workspace; there was no prior repository
  history.
- The shared handoff contract is `AGENTS.md`; `CLAUDE.md` imports it.
- The local pipeline is present through ingest, enrichment, scoring/verdicts, and outcome
  capture. Static HTML prototypes are also present. Supabase support exists as source code and
  SQL only; no Supabase operation was run during this foundation pass.
- `supabase/.env` is ignored. Its `SUPABASE_SERVICE_ROLE_KEY` entry is malformed (value
  withheld) and requires explicit user-approved correction. No credentials were changed or
  exposed.
- `supabase/apply_schema.py` must not be run: it disables TLS certificate and hostname
  verification.
- Shared local verification: `scripts/check.sh`.
