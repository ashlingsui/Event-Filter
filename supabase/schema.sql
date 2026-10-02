-- Event Filter — Supabase schema
-- Written 2026-09-21. Implements SPEC.md §1 (frozen taxonomy), §1b (intent), §1c (read-back),
-- §4 (three layers + privacy boundary), §5 (multi-user, public sign-up).
--
-- THE ONE RULE THIS SCHEMA EXISTS TO ENFORCE:
--   Shared  = event catalog + pooled archetype statistics. No names, no individual outcomes.
--   Private = every outcome, every contact, every felt note. Owner-only, always.
-- A user must never be able to learn that another user met someone and chose not to follow up.

-- ============================================================================
-- ENUMS — these mirror SPEC.md. Changing a value is a schema migration, not a tweak.
-- ============================================================================

create type source_kind     as enum ('luma','campusgroups','partiful','manual');
create type event_format    as enum ('build_night','hackathon','demo_day','workshop',
                                     'panel','fireside','mixer','lecture','class','office_hours',
                                     'unknown');
create type host_tier       as enum ('tier1_vc','scaled_co','startup','student_club','unknown');
create type proximity       as enum ('none','wrong_ladder','some','high');
create type saturation      as enum ('none','some','high');
create type hook_kind       as enum ('none','topic','person');
-- 'unscored' added 2026-10-01 (SPEC.md §3c) — "an event the model knows nothing about must never
-- receive a confident skip OR a confident go." Values may be added to this enum, never redefined
-- (SPEC.md §1 freeze rule) — if this schema is already live elsewhere, add it via
-- `alter type verdict_kind add value 'unscored'` (see supabase/migrations/) rather than re-running
-- this file, which is deliberately not idempotent.
create type verdict_kind    as enum ('go','part','go_if','wildcard','skip','suppressed','blocked','unscored');
create type reason_code     as enum ('not_reachable','conflict','quota_full','spectator',
                                     'wrong_ladder','recurring','off_phase','below_bar');
create type intent_kind     as enum ('want','pass','undecided');
create type rsvp_kind       as enum ('none','applied','waitlisted','confirmed','rejected');
create type label_state     as enum ('unknown','partial','labeled');
create type label_origin    as enum ('prospective','retrospective_backfill');
create type phase_kind      as enum ('build','interview');

-- ============================================================================
-- LAYER 3 — PROFILES. Per user. Everything the model cannot compute without asking.
-- Populated by onboarding (SPEC.md §5): four questions, each tied to a field below.
-- ============================================================================

create table profiles (
  id              uuid primary key references auth.users(id) on delete cascade,
  created_at      timestamptz not null default now(),
  onboarded_at    timestamptz,

  -- Q1 "Where do you live and how do you get around?" -> cost_blocks, reachable, go_if
  home_city       text not null,
  home_lat        double precision,
  home_lng        double precision,
  drives          boolean not null default false,
  has_ride_access boolean not null default false,   -- friends who drive; enables go_if

  -- Q2 "What are you optimizing for?" -> target_proximity
  target_role      text,
  target_industry  text[] not null default '{}',    -- 'ai', 'fintech', ...
  target_companies text[] not null default '{}',
  needs_sponsorship boolean not null default false,

  -- Q3 "What community are you already in?" -> cohort_saturation
  home_community  text,                             -- e.g. 'Haas MBA 2028'

  -- Q4 "How many evenings a week?" -> weekly quota
  weekly_slots    smallint not null default 2 check (weekly_slots between 0 and 14),

  -- asked once in passing, not in the form
  phase           phase_kind not null default 'build',
  free_weekdays   smallint[] not null default '{}', -- 0=Mon .. 6=Sun; Ashling: {4}

  schema_version  smallint not null default 1
);

-- ============================================================================
-- SHARED — EVENT CATALOG. Same rows for everyone. Written only by the pipeline.
-- The artifact/browser can never fetch Luma (CSP), so ingest stays local and pushes here.
-- ============================================================================

create table events (
  id              uuid primary key default gen_random_uuid(),
  source          source_kind not null,
  source_id       text not null,
  url             text not null,
  name            text not null,
  description     text,

  start_at        timestamptz not null,
  end_at          timestamptz,
  duration_hr     numeric(4,1),

  venue           text,
  city            text,
  lat             double precision,
  lng             double precision,

  host_names      text[] not null default '{}',
  host_tier       host_tier not null default 'unknown',
  format          event_format not null default 'unknown',
  size            integer,                          -- null = hidden on the listing
  gated           boolean not null default false,   -- approval/capacity => apply early
  recurring       boolean not null default false,
  next_occurrence timestamptz,

  -- RECORDED-BUT-UNWEIGHTED (SPEC.md §1c). Nothing reads these for scoring yet.
  speakers        jsonb not null default '[]',      -- [{name,title,employer}]

  ingested_at     timestamptz not null default now(),
  schema_version  smallint not null default 1,
  unique (source, source_id)
);
create index on events (start_at);
create index on events (city);

-- ============================================================================
-- PER-USER SCORING. Append-only history — the model re-runs, so scores change.
-- predicted_p is NEVER updated in place. The value that counts for calibration is
-- copied into outcomes at decision time (see outcomes.predicted_p_locked).
-- ============================================================================

create table event_scores (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references auth.users(id) on delete cascade,
  event_id      uuid not null references events(id) on delete cascade,
  scored_at     timestamptz not null default now(),
  model_version text not null,

  predicted_p   numeric(4,3) check (predicted_p between 0 and 1),
  -- SPEC.md §3c — fraction of scoring-relevant judgment fields actually known. Drives the
  -- `unscored` verdict gate in score/verdicts.py; stored so a past low-confidence score stays
  -- explainable rather than looking like an ordinary, fully-informed one.
  confidence    numeric(3,2) check (confidence between 0 and 1),
  verdict       verdict_kind not null,
  primary_reason reason_code,
  reasons       reason_code[] not null default '{}',

  -- person-relative features (SPEC.md §4: these do NOT pool)
  participant       boolean,
  target_proximity  proximity,
  cohort_saturation saturation,
  prior_hook        hook_kind,
  companions        text[] not null default '{}',
  trip_chained      boolean not null default false,
  cost_blocks       numeric(3,1),
  bart_walk_min     integer,
  reachable         boolean,

  is_exploration boolean not null default false,    -- the ~1-in-7 wildcard
  why            text,                              -- human-readable factor breakdown
  schema_version smallint not null default 1
);
create index on event_scores (user_id, event_id, scored_at desc);

-- ============================================================================
-- INTENT (SPEC.md §1b). Her want/pass judgment. A PREFERENCE label, never an outcome.
-- Recorded for events she never attends — the only signal that exists on a skipped event.
-- ============================================================================

create table intents (
  user_id         uuid not null references auth.users(id) on delete cascade,
  event_id        uuid not null references events(id) on delete cascade,
  intent          intent_kind not null,
  intent_at       timestamptz not null default now(),
  intent_anchored boolean not null default true,    -- was the verdict visible when marked
  rsvp_state      rsvp_kind not null default 'none',
  schema_version  smallint not null default 1,
  primary key (user_id, event_id)
);

-- ============================================================================
-- OUTCOMES — PRIVATE. The frozen taxonomy (SPEC.md §1). Owner-only, no exceptions.
-- ============================================================================

create table outcomes (
  user_id   uuid not null references auth.users(id) on delete cascade,
  event_id  uuid not null references events(id) on delete cascade,

  attended  boolean not null default false,
  partial   boolean not null default false,

  -- FROZEN COPY of the prediction live at decision time. Never updated after insert.
  -- This is why re-scoring can't corrupt the calibration record.
  predicted_p_locked numeric(4,3),
  locked_at          timestamptz,

  -- T+0/T+1
  felt_score         smallint check (felt_score between 0 and 10),
  felt_note          text,
  felt_captured_at   timestamptz,

  -- T+7 / T+30. NULL means UNKNOWN, not false (SPEC.md §1 missing-data policy).
  s1_pov     boolean,
  s2_contact boolean,
  s3_build   boolean,
  s4_cohort  boolean,
  details    jsonb not null default '{}',           -- the required "what/who" per stream

  -- Three-valued on purpose: NULL OR TRUE = TRUE, FALSE OR FALSE = FALSE,
  -- NULL OR FALSE = NULL. Unknown stays unknown instead of silently becoming a miss.
  hit boolean generated always as (s2_contact or s3_build) stored,

  label_status label_state  not null default 'unknown',
  label_source label_origin not null default 'prospective',
  t7_due       timestamptz,
  t30_due      timestamptz,

  -- SPEC.md §4 caution 1: two friends at the same event are ~one observation, not two.
  co_attendee_ids uuid[] not null default '{}',

  schema_version smallint not null default 1,
  primary key (user_id, event_id)
);

-- predicted_p_locked is write-once. Enforced, not merely documented.
create or replace function freeze_locked_prediction() returns trigger
language plpgsql as $$
begin
  if old.predicted_p_locked is not null
     and new.predicted_p_locked is distinct from old.predicted_p_locked then
    raise exception
      'predicted_p_locked is immutable (SPEC.md §1). Prediction was %, refused change to %.',
      old.predicted_p_locked, new.predicted_p_locked;
  end if;
  return new;
end $$;

create trigger outcomes_freeze_prediction
  before update on outcomes
  for each row execute function freeze_locked_prediction();

-- ============================================================================
-- CONTACTS — PRIVATE, the most sensitive table in the system. Never pooled, ever.
-- ============================================================================

create table contacts (
  id        uuid primary key default gen_random_uuid(),
  user_id   uuid not null references auth.users(id) on delete cascade,
  event_id  uuid references events(id) on delete set null,
  name      text not null,
  org       text,
  role      text,
  state     text,                                   -- 'met','messaged','warm','offered', ...
  convening_power boolean,                          -- LESSONS.md #23, recorded unweighted
  notes     text,
  created_at timestamptz not null default now()
);

-- ============================================================================
-- HYPOTHESES (SPEC.md §1c). Suspected, not applied, until supported across >=3 events.
-- ============================================================================

create table hypotheses (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade,
  statement  text not null,
  protected  boolean not null default false,        -- touches the frozen taxonomy => can NEVER act
  status     text not null default 'pending',
  supporting_event_ids uuid[] not null default '{}',
  evidence   jsonb not null default '[]',
  created_at timestamptz not null default now()
);

-- ============================================================================
-- LAYER 2 — SHARED PRIOR. The only thing learned from everyone's data.
-- Written ONLY by the aggregation job below. Individual outcomes never leave their owner.
-- ============================================================================

create table archetype_stats (
  archetype      text primary key,                  -- e.g. 'build_night|small|participant'
  format         event_format not null,
  size_bucket    text not null,                     -- 'small','medium','large','unknown'
  participant    boolean,
  n_observations integer not null,
  n_users        integer not null,
  n_hits         integer not null,
  hit_rate       numeric(4,3) not null,
  felt_mean_z    numeric(5,3),                      -- per-user normalized (§4 caution 2)
  computed_at    timestamptz not null default now()
);

-- ============================================================================
-- ROW LEVEL SECURITY. Deny by default on every table.
-- ============================================================================

alter table profiles        enable row level security;
alter table events          enable row level security;
alter table event_scores    enable row level security;
alter table intents         enable row level security;
alter table outcomes        enable row level security;
alter table contacts        enable row level security;
alter table hypotheses      enable row level security;
alter table archetype_stats enable row level security;

-- Own-row-only tables. This is the §4 privacy boundary, in four words: user_id = auth.uid().
create policy own_profile    on profiles      for all using (id = auth.uid())      with check (id = auth.uid());
create policy own_scores     on event_scores  for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy own_intents    on intents       for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy own_outcomes   on outcomes      for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy own_contacts   on contacts      for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy own_hypotheses on hypotheses    for all using (user_id = auth.uid()) with check (user_id = auth.uid());

-- Shared, read-only to users. Writes come from the pipeline via the service role,
-- which bypasses RLS — so there is deliberately no insert/update policy here.
create policy read_events     on events          for select using (auth.uid() is not null);
create policy read_archetypes on archetype_stats for select using (auth.uid() is not null);

-- ============================================================================
-- THE POOLING JOB. Reads private rows as a privileged role, publishes only aggregates.
-- This function is the single point where private data touches shared data — audit it here.
-- ============================================================================

create or replace function recompute_archetype_stats()
returns void
language plpgsql
security definer                                   -- reads across users; nothing else may
set search_path = public
as $$
begin
  delete from archetype_stats;

  insert into archetype_stats
    (archetype, format, size_bucket, participant,
     n_observations, n_users, n_hits, hit_rate, felt_mean_z, computed_at)
  select
    e.format || '|' || sb.bucket || '|' || coalesce(s.participant::text,'unknown'),
    e.format,
    sb.bucket,
    s.participant,
    count(*),
    count(distinct o.user_id),
    count(*) filter (where o.hit),
    round(count(*) filter (where o.hit)::numeric / count(*), 3),
    round(avg(z.felt_z), 3),
    now()
  from outcomes o
  join events e on e.id = o.event_id
  left join lateral (
    select distinct on (es.user_id, es.event_id) es.participant
    from event_scores es
    where es.user_id = o.user_id and es.event_id = o.event_id
    order by es.user_id, es.event_id, es.scored_at desc
  ) s on true
  cross join lateral (
    select case
      when e.size is null then 'unknown'
      when e.size <= 50   then 'small'
      when e.size <= 150  then 'medium'
      else 'large' end as bucket
  ) sb
  -- §4 caution 2: felt scores are not comparable across people. Normalize within user.
  left join lateral (
    select (o.felt_score - avg(o2.felt_score) over ())
           / nullif(stddev_samp(o2.felt_score) over (), 0) as felt_z
    from outcomes o2 where o2.user_id = o.user_id limit 1
  ) z on true
  where o.hit is not null                          -- unknown stays excluded (§1)
    and o.label_source = 'prospective'             -- backfills train, they don't pool
  group by e.format, sb.bucket, s.participant
  -- K-ANONYMITY GUARD. Without this, an archetype with n=1 publishes one person's
  -- outcome to everyone. Do not relax these thresholds.
  having count(*) >= 5 and count(distinct o.user_id) >= 2;
end $$;

-- `revoke ... from public` is NOT sufficient on Supabase: the platform grants EXECUTE to the
-- `anon` and `authenticated` roles by default, so those grants survive a PUBLIC revoke. Verified
-- against the live database 2026-09-21 — the ACL still read {anon=X, authenticated=X} after the
-- line below alone. This function is SECURITY DEFINER and reads EVERY user's private outcomes,
-- so it must only be callable by the scheduled job (service_role) and the owner.
revoke all on function recompute_archetype_stats() from public;
revoke execute on function recompute_archetype_stats() from anon, authenticated;

-- ============================================================================
-- NOT IN THIS SCHEMA, ON PURPOSE
--
-- 1. No table stores "what counts as a hit." That is code, and it is frozen (SPEC.md §1).
--    If it ever becomes a row someone can edit, every user's history stops being comparable.
-- 2. No cross-user read of outcomes or contacts exists, for anyone, including the owner
--    of the project. Pooling happens only through recompute_archetype_stats().
-- 3. Backfilled rows (label_source='retrospective_backfill') are excluded from pooling and
--    must never be counted in a calibration rate — they have no predicted_p_locked.
-- ============================================================================

-- ============================================================================
-- AMENDED 2026-09-21 — PER-USER SOURCES, and ingest moves server-side.
--
-- Supersedes the note above that ingest must stay local. That was a constraint of the
-- ARTIFACT runtime (CSP), and this is a normal web app. A serverless function (Vercel or
-- Supabase Edge) fetches Luma / CampusGroups server-side — no CORS applies server-to-server.
-- The browser still cannot fetch them directly; the function can.
--
-- The real reason to move it: a local pipeline is a single point of failure for a
-- multi-user product. Friends' data goes stale whenever Ashling's laptop is closed.
--
-- NOTE: there is no "connect your Luma account" OAuth to build. The feeds we use are
-- PUBLIC per-calendar endpoints (api.lu.ma/ics/get?entity=calendar&id=cal-XXXX). A user
-- does not log in to Luma; they subscribe to calendar IDs. Their personal RSVP'd-events
-- calendar is deliberately NOT the source — see BUILD_HANDOFF.md.
-- ============================================================================

alter table events add column calendar_id text;      -- 'cal-XXXX', or campusgroups subdomain
create index on events (calendar_id);

create table user_calendars (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade,
  source     source_kind not null,
  calendar_id text not null,                          -- Luma cal-XXXX, or 'haas' for CampusGroups
  label      text,
  added_by   text not null default 'default',         -- 'default' | 'user' | 'discovered'
  active     boolean not null default true,
  created_at timestamptz not null default now(),
  unique (user_id, source, calendar_id)
);

alter table user_calendars enable row level security;
create policy own_calendars on user_calendars for all
  using (user_id = auth.uid()) with check (user_id = auth.uid());

-- The event catalog stays GLOBAL (union of everyone's calendars) so it dedupes and so
-- archetype pooling runs over one shared catalog. Each user simply sees the subset from
-- calendars they subscribe to.
create or replace view my_events as
  select e.* from events e
  join user_calendars uc
    on uc.calendar_id = e.calendar_id
   and uc.user_id = auth.uid()
   and uc.active;

-- ONBOARDING STAYS FOUR QUESTIONS (SPEC.md §5). Do not add a fifth for calendars.
-- Seed user_calendars from the answers instead:
--   home_city ~ Berkeley/SF  -> the curated participant-side set (OpenRouter, Claude
--                               Workshops, Claude Community, Codex SF, South Park Commons,
--                               Stripe Developer Meetups)
--   home_community ~ Haas    -> campusgroups 'haas'
--   target_industry          -> narrows or extends the default set
-- Then expose "add a calendar" afterwards, added_by='user'. Defaults first, configuration later.
--
-- A user at another school: CampusGroups instances follow <school>.campusgroups.com with the
-- same unauthenticated endpoint, so adding a school is one row, not a new integration. A user
-- at a school without CampusGroups simply gets no campus source.
