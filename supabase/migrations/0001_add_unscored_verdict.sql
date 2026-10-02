-- Migration: add 'unscored' to verdict_kind, add event_scores.confidence.
-- SPEC.md §3c, 2026-10-01 — "an event the model knows nothing about must never receive a
-- confident skip OR a confident go." Only needed if supabase/schema.sql was already applied to a
-- live database before this date; a fresh apply_schema.py run already includes both changes.
--
-- Not run automatically by anything in this repo — no live Supabase operation runs without
-- explicit authorization (AGENTS.md). Apply by hand against the real database:
--   set -a; source supabase/.env; set +a
--   psql "$SUPABASE_DB_HOST ..." -f supabase/migrations/0001_add_unscored_verdict.sql
-- (or run the two statements below through whatever client already has a verified connection —
-- see supabase/apply_schema.py for this project's TLS-verification requirements.)

alter type verdict_kind add value if not exists 'unscored';
alter type event_format add value if not exists 'office_hours';

alter table event_scores
  add column if not exists confidence numeric(3,2) check (confidence between 0 and 1);
