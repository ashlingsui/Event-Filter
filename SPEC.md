# Event Filter — v0.2 spec (LOCKED)

Drafted 2026-09-17. Grilled and locked 2026-09-18.

This document pins **only the decisions that are expensive to change.** Everything not in here
(weights, UI, calendar list, the scoring formula itself) is deliberately unspecified, because
those are cheap to change and better decided against real data.

**The freeze is what makes learning possible.** A system that learns needs a stationary target;
if the label drifts, nothing can learn and you just get noise that looks like progress.

---

## Purpose

Decide which Bay Area AI/tech events are worth Ashling's time, explain why, prepare her for the
ones she picks, and learn from what actually happens afterward.

The real job is not filtering. It is *permission to say no* with defensible grounds.

Framing line for the UI:
> **"Is this event for someone like me, or am I watching someone else's event?"**

---

## §1 OUTCOME TAXONOMY — FROZEN

This is the label. Redefine it mid-collection and every prior row becomes inconsistent.

### Three capture points

| When | What | Mechanic |
|---|---|---|
| **T+0/T+1** | `felt_score` 0-10 + one free-text line | Push, same night |
| **T+7** | Three yes/no questions | Push, **recognition not recall** |
| **T+30** | Batch sweep of rows still open | One screen, all rows, tick down |

**Recognition, never recall.** Never ask "who did you meet?" Always show the scraped speaker
names and logged contacts and ask "any of these?" Recall fails; recognition survives.

### The four streams

| Stream | Question | Counts toward `hit`? |
|---|---|---|
| **S1 — POV** | Can I name the specific claim, and does it appear in writing (note, message, interview answer) within 7 days? | **No** |
| **S2 — Contact** | Have I exchanged messages since with someone from this event, or is someone now `warm` in `contacts.csv`? | **Yes** |
| **S3 — Build** | Did I start or ship something traceable to this event? | **Yes** |
| **S4 — Cohort** | Did this strengthen a friendship or cohort tie I care about? | **No** |

**`hit` = S2 OR S3.**
**`predicted_p` = P(contact or build).** Expect honest zeros — that is the point.

S1 and S4 are recorded on every event. They are real value; they just don't justify travel.

### The allocation rule

> **Campus events exist to serve S1 and S4. Trips out of Berkeley must clear the bar on S2 or S3.**

S1 is cheap to satisfy locally (the Meta data lead, on campus, at lunch, free food). Driving an
S1 need into justifying an SF trip is how the system talks you into bad decisions.

**Clarified 2026-09-21 — this is a statement of purpose, not an exemption from the quota.** The
weekly slot quota (§3, not frozen) originally read this rule as also exempting campus from
`GO_BAR`, so a single campus event in an otherwise-empty week won its own week's slot uncontested
regardless of value — Story Salon alone produced 8 automatic "go"s across 8 different weeks, ~0
real S2/S3 value in any of them. Confirmed with her 2026-09-21: no exemption. Campus events compete
in the same unified weekly quota as off-campus trips, ranked by `(value - cost_blocks)` like
everything else — clearing `GO_BAR` is what makes ANY event a candidate, campus included. What
survives from the rule above is the *reason campus attendance is worth having* (S1/S4, real value
that doesn't count toward `hit`), not a scoring carve-out. See `score/verdicts.py` for the
mechanism this describes.

### Explicitly struck from the model

> **"You could get this online" is not a valid discount.**

Ashling does not consume content she bookmarks. She consumes what she attends. In-person is a
**commitment device**, and that is a real mechanism, not a rationalization. This applies to both
S1 (opinions) and S3 (demos).

### Missing-data policy — FROZEN

Unanswered = **`unknown`**. Excluded from the fit, counted and displayed.

The UI shows "14 events · 11 labeled · 3 unknown." If unknowns exceed 30%, the calibration panel
**refuses to show a hit rate** and says why. This is Ashling's own standard, from `TRACKER.md` §3:
*"report raw counts alongside every rate, always."*

Treating silence as "no outcome" would teach the model everything fails. Treating it as a dropped
row would bias toward memorable events, which are the hits. Neither is neutral, so: unknown.

### Freeze rule

Definitions and horizons do not change once collection starts. Fields may be **added**; existing
fields are **never redefined**. Every row carries `schema_version` so that if something must
change, old rows stay interpretable rather than silently corrupted.

### §1b INTENT — added 2026-09-18 (permitted: new fields, nothing redefined)

Her own want/pass judgment, captured at decision time. **This is a preference label, not an
outcome. It never enters `hit`.**

```
intent            want | pass | undecided
intent_at         timestamp
intent_anchored   bool — was the model's verdict visible when she marked it?
gated             bool — RSVP requires approval or has capacity
rsvp_state        none | applied | waitlisted | confirmed | rejected
```

**Why this matters more than it looks:**

1. It is the **gut** side of the gut-vs-model comparison, which was the original point of the
   project. Without it, calibration only compares *model* to outcome — never her.
2. It is high-volume. ~40 intents a week against 2-4 outcome labels. It is the only label that
   accrues fast enough to learn a preference function from.
3. **It is the only signal available on events she does NOT attend** — which partially repairs
   the counterfactual blind spot in §3. Outcomes for skipped events are unknowable forever;
   preferences are not.

**`rejected` ≠ `pass`.** Wanting to go and not getting in is not a preference signal against the
event, and must never be counted as a skip in any rate. Gated events are disproportionately the
small high-value ones, so `gated = true` is also a latency signal: apply early.

**Anchoring, stated honestly:** the verdict leads the UI by design (§Reasons argue, rules decide),
so most intents will be anchored by it. We record `intent_anchored` rather than pretending
otherwise. Note the asymmetry when reading results: anchoring *suppresses* disagreement, so a high
model-vs-intent disagreement rate is credible evidence, while a low one is ambiguous. Capture the
wildcard/exploration picks blind where practical.

**Second calibration story this unlocks:** wanted vs. delivered. "You wanted 18 events this month;
you attended 4; the ones you wanted most were not the ones that produced anything." That is the
most directly disarming evidence the system can produce against FOMO.

**It also fixes the un-scrapable field problem.** `trip_chained`, `companions` and `prior_hook`
cannot be scraped — they are personal context no crawler sees, and defaulting them to null makes
the model systematically blind (this is the leading suspect in the 0.20-vs-0.60 gap on the
OpenRouter event). The want/pass moment is exactly when to collect them: marking "want" opens a
three-tap strip — *have a ride? · going with someone? · already use this?* — and the verdict
recomputes.

---

## §1c THE READ-BACK LOOP — added 2026-09-20

She gives feedback in natural language; the system reads back what it heard and asks whether
anything should change. Her request, and it's the right shape — but it has one failure mode that
must be engineered out.

### Two panes, never mixed

| **Recorded** | **Suspected** |
|---|---|
| Extraction. Facts from what she said. | Inference. Patterns the system thinks it sees. |
| `felt_score = 8`, `companions = [Ivy]`, `cost_blocks = 0`, 3 contacts forming | "Content quality may not predict your outcomes" |
| She **corrects** these. Applied immediately. | She **cannot approve** these yet. They accumulate. |

Mixing them is the trap: if a correct fact sits next to a speculative inference, she rubber-stamps
the inference because the facts around it are right.

### Proposals accumulate; they do not apply

A hypothesis raised once is logged with a counter and changes nothing. It becomes an actionable
proposal only after the **same** hypothesis is independently raised across **≥3 events**.

> **Worked example, 2026-09-18.** Walking out of the OpenRouter event she said *"the fact that it's
> in SF doesn't matter that much."* Had the UI asked "should I change the filtering algorithm?"
> that night, she would have said yes — and the cost model would have been gutted on one vivid
> data point, at an event that happened to cost zero. See `LESSONS.md` #24.

The pending-hypothesis list is itself a UI surface: *things the system suspects but has not earned
the right to act on.*

### Record early, weight late

Recording a new field is free and **cannot be backfilled** — you can never learn about a variable
you didn't write down. Weighting it is expensive and needs evidence. So they are separate decisions:

- **New field** → start recording immediately, influences nothing.
- **Weight on that field** → only after the hypothesis clears the ≥3 threshold.

First case: `convening_power` — begin recording it on every event now. See `LESSONS.md` #23.

### Change tiers — what the UI may and may not offer

| Tier | Example | Rule |
|---|---|---|
| Field correction | `cost_blocks` 1 → 0 | Apply immediately. It's a fact. |
| New field | add `convening_power` | Record immediately, weight = 0. |
| Weight change | down-weight content quality | Requires ≥3 supporting events. |
| Outcome definition | "should a good conversation count as a hit?" | **Never offerable. Not a setting.** |

**The freeze must be enforced in the product, not just in this document.** The UI must never present
the outcome definition or the T+7/T+30 horizons as adjustable — not greyed out, not behind a
confirm, simply absent. Otherwise it becomes negotiable at 11pm after a good event, and every row
collected before that night becomes incomparable.

Reasons argue, rules decide — applied to the spec itself.

---

## §2 EVENT SCHEMA

### Pre-event — must be knowable *before* the decision. No leakage.

```
schema_version, id, source (luma | campusgroups | partiful), url, name
start, end, duration_hr
venue, city, lat, lng, bart_walk_min, reachable        # reachable = hard filter
host_names[], host_tier (tier1_vc | scaled_co | startup | student_club | unknown)
format (build_night | hackathon | demo_day | workshop | panel | fireside | mixer | lecture | class | office_hours)
size (guest_count, or bucket when hidden)

participant (bool)          # can I legitimately DO the thing this event is for? → drives S3
target_proximity            # density of people CURRENTLY INSIDE my target companies,
                            # or one hop out. → drives S2
                            # (none | some | high | wrong_ladder)
cohort_saturation           # share of room I already know (none | some | high)
prior_hook                  # none | topic | person
companions[]                # POSITIVE multiplier, never a cost
trip_chained (bool)         # already on a path I'm taking
cost_blocks (0 | 0.5 | 1 | 1.5 | 2)
recurring (bool), next_occurrence
phase (build | interview)
predicted_p                 # recorded BEFORE. NEVER edited.
is_exploration (bool)       # see §3
```

**`target_proximity` is not seniority and not affiliation.** A Haas EWMBA/EMBA mixer can score
higher than an SF startup mixer, because those classmates *currently work* at target companies.
Operational rule: **EWMBA/EMBA events are S2 events; FTMBA events are cohort events.**
`wrong_ladder` = people ahead of you on a ladder you are not climbing (the Founder & Funder case).

Ranking for S2: `one-step-ahead` > `far-ahead`. Far-ahead rooms (a16z partners, famous founders)
pay off **later**, once there are projects worth reaching out about — so their value is deferred
and contingent on the build bottleneck clearing.

### Post-event
```
attended (bool), partial (bool)
felt_score, felt_note                       # T+0/T+1
s1_pov, s2_contact, s3_build, s4_cohort + "what/who"
hit (derived = s2 OR s3)
label_status (labeled | unknown)
```

---

## §3 LEARNING DESIGN

### The hard limit: no counterfactuals

If the model says skip and she skips, it never finds out it was wrong. Feedback arrives only for
attended events, so a naively self-evolving system becomes **self-confirming** — it narrows onto
what it already believes and grows more confident while getting worse.

### Exploration policy

> **Roughly 1 in 6-8 attendances is a wildcard**: an event the model scored *low*, attended
> anyway, flagged `is_exploration = true`.

This is the only mechanism by which the model can discover it is wrong. It doubles as a product
feature — a sanctioned wildcard slot, which serves the FOMO goal directly: going to something
random is *part of the system*, not a lapse in discipline.

Exploration rows are held out of the fit's error reporting but included in learning.

### Multi-user (designed for, not built yet)

Per-user n stays tiny (2-4 events/week). One user's data alone cannot fit meaningful weights —
that part is theater. Across users it isn't:

- Learn a **shared prior over event archetypes** (build night, mixer, panel, demo day, class)
  pooled across all users.
- Learn a small **per-user offset** from that individual's rows.

Partial pooling means a new user needs ~10 labeled events to personalize, not 200. This is the
cold-start answer and it is what makes this a product rather than a script.

**Consequence:** the schema freeze matters *more* under multi-user, because pooling requires the
label to mean the same thing across people. Build single-user; design the schema as if multi-user.

### Not frozen

Scoring formula, all weights, calibration method, calendar list, UI, alert thresholds, phase
definitions, and the hard-filter set.

### Reachability is a cost, not a gate — revised 2026-09-20

**Superseded:** `reachable == false → reject`. Her correction, and it's right: *"SF venues should
still be considered if the other qualities of the event are actually high. I'll figure out a way
to go or carpool with friends."* Not BART-reachable does not mean unattendable — it means a ride
has to be arranged. That is friction, not impossibility, and the OpenRouter event is the proof
(Ivy drove).

**New behaviour — conditional verdicts:**

- `reachable == false` adds a large `cost_blocks` penalty instead of rejecting.
- An unreachable event surfaces **only if it would rank top-3 that week anyway.** The bar for a
  conditional GO is *higher* than for a normal GO, not lower — otherwise the 63 currently-blocked
  events flood back in and the page stops being a decision surface.
- Below that bar it is **suppressed**, not blocked: it stays out of the stack but is counted in
  the summary (`suppressed_summary`), so coverage is never silently lost.
- When it does surface, the verdict is **`go_if`** and it states the unblocking condition as an
  action: *"GO — if you can get a ride. Ivy is going to two other Tech Week events that week."*

**General principle this establishes:** when an event fails on a *solvable* constraint, say what
would have to be true instead of dropping it. Applies beyond transport — RSVP closing, a movable
conflict, a companion needed. A silent block teaches nothing; a conditional tells her what to go
fix.

**Genuinely impractical stays out.** A ride solves Palo Alto. It does not solve a two-hour drive
each way on a school night — distance still scales continuously in `cost_blocks`.

*Noted for her own calibration:* this is a loosening argued for immediately after a good event,
which is the same shape as the "SF doesn't matter" update that `LESSONS.md` #24 flags. It is
accepted here because the argument is **structural** (transport is solvable, and she has already
solved it twice) rather than **evidential** (one good night). Worth re-checking at n=10 whether
`go_if` events actually convert, or whether this was the anxiety negotiating.

---

## §4 OUT OF SCOPE FOR v0

- **Follow-up tracking** — lives in Ashling's recruiting pipeline dashboard. This system picks the
  room; it does not own conversion.
- Auto-RSVP, calendar writes, any action taken on her behalf.
- **Read-only exception (pending her confirmation):** the event filter may *read* `contacts.csv`
  to auto-propose S2 labels for confirmation. It never writes.

---

## §5 KNOWN COVERAGE LIMITS

Luma has no global search. Recall is exactly the union of followed calendars, so the UI must say
"everything on your calendars," never "everything." A discovery strip surfaces newly-seen
calendars. Partiful is a separate ingest. Campus comes from
`haas.campusgroups.com/mobile_ws/v17/mobile_events_list` (no auth required).

---

## §6 RESOLVED BY GRILLING (2026-09-18)

1. ~~`hit` as OR across unequal outcomes~~ → S2 OR S3 only.
2. ~~S1 unfalsifiable~~ → demoted, given a falsifiable form, allocated to campus.
3. ~~`audience_fit` as one blended judgment~~ → split into `participant` + `target_proximity`.
4. ~~"peers can't help"~~ → **wrong**; EWMBA/EMBA classmates work at target companies.
5. ~~T+14 horizon~~ → T+0/T+7/T+30, recognition-based.
6. ~~Missing data~~ → `unknown`, excluded and displayed.
7. ~~Weight-fitting at low n is theater~~ → true single-user; solved by pooling across users.
8. ~~No counterfactuals~~ → forced exploration, ~1 in 6-8.

### Still open (cheap, revisit with data)

- `prior_hook` is scored pre-event but is manufacturable by prep. Feature, intervention, or both?
  Does prep contaminate the label?
- Phase transitions: who flips `build` → `interview`, and on what trigger?
- Alert thresholds and how noisy push is allowed to be.
- Calendar-list maintenance cadence.
- What the frontend must prove to a recruiter reading it cold.

---

## §4 MULTI-USER — added 2026-09-21

Built for Ashling and a handful of friends, each on their own laptop. Her framing, confirmed
2026-09-21: *"there are common labels and standards and rules of what a good event is... but the
self-evolving system should be personalized for everyone."* Correct — with one split made explicit
below, because two things are being called "shared" and only one of them is allowed to move.

### Three layers, not two

| Layer | What | Who it's the same for | Can it change? |
|---|---|---|---|
| **1 — Standards** | The taxonomy. `hit` = S2 OR S3. Felt vs delivered. T+0/T+7/T+30. Reason codes. Schema. | Everyone, identically | **No. Frozen (§1).** |
| **2 — Shared prior** | Archetype base rates learned from pooled data: "small hands-on build nights convert; 200-person mixers don't." | Everyone, identically | **Yes — this is what learns.** |
| **3 — Personal** | Weights/offsets, and the profile: industry, target role, transport, calendar, phase. | Per user | Yes, per user |

**Layer 1 must never be moved by layer 2.** Pooled learning may update how strongly a format
predicts an outcome. It may never update what counts as an outcome. If the definition drifts under
learning pressure, every user's history becomes mutually incomparable and pooling — the entire
reason for multi-user — stops working.

### Which features pool, and which don't

- **Pool (structural, person-independent):** `format`, `size`, `participant`, `cohort_saturation`,
  `recurring`, `gated`, duration, time-of-day. These describe the *shape* of an event. A hands-on
  build night behaves like a hands-on build night regardless of whose career it is.
- **Do not pool (semantic, person-relative):** `target_proximity`, `prior_hook`, `phase`,
  `cost_blocks`. A room full of Stripe people is high proximity for a fintech friend and moderate
  for Ashling. Cost depends on who drives and whose Friday is free.

Industry focus (AI, fintech, …) is a **layer-3 profile field**, used to compute
`target_proximity` per user — not a separate model. One model, different inputs per person.

### Privacy boundary — non-negotiable

- **Shared:** archetype statistics. Aggregates over event shapes. No names.
- **Never shared:** contact notes, who someone met, who they followed up with, felt notes about
  named people, anything in `contacts.csv`.

Ashling's own `TRACKER.md` already sets the standard — *"write nothing you would not want the
person to read"* — and the stakes rise once five people share a system. A friend must never be
able to see that she met someone and chose not to follow up.

### Two statistical cautions that get missed

1. **Co-attendance is not independent evidence.** If Ashling and Ivy attend the same event and both
   log it, that is close to one observation, not two. Correlated rows inflate apparent evidence at
   exactly the sample sizes where it matters most. Record `co_attendees[]` and discount accordingly
   when pooling.
2. **Felt scores are not comparable across people.** One person's 8 is another's 6. Normalize
   within user (rank or z-score) before any felt-vs-delivered comparison crosses a user boundary.
   Raw felt scores pool badly.

---

## §5 MULTI-USER ARCHITECTURE & COLD START — added 2026-09-21

### It can be built with no backend

Verified 2026-09-21 against the artifact runtime contract. Three capabilities carry the whole
multi-user design:

| Capability | What it gives us |
|---|---|
| **`db`** | Server-side JSON doc store. Shared collections readable by signed-in viewers; writes gated by access level. |
| **`user`** | Identity — who is viewing, opaque per-org id, access checks. |
| **`sample`** | The page can ask Claude. This is what extracts structure from free-text feedback, in the page, with no server. |

**The privacy boundary is enforced by the platform, not by us.** Each viewer's `data/users/<id>/`
subtree is private *even from the artifact's owner*. So:

- `archetypes/…`, `events/…` → shared collections. Pooled statistics, event rows, no names.
- `data/users/me/outcomes`, `data/users/me/contacts` → private per user. Contact notes, who they
  met, who they chose not to follow up with. Ashling cannot see her friends' rows and they cannot
  see hers.

That is exactly the boundary agreed in §4, and it does not have to be engineered — it is the
storage model.

### What still runs locally

The artifact **cannot fetch Luma or CampusGroups** (CSP blocks cross-host fetch). So:

- **Local, scheduled:** ingest → enrich → score. Unchanged, the existing Python pipeline.
- **Artifact:** display + capture. Scored events are pushed into the artifact's `db` (`write_db`)
  after each run; viewers see verdicts, mark want/pass, and give free-text feedback which lands
  back in `db` for Ashling to read (`read_db`).

### Access constraint — name it before inviting anyone

Friends must be **actual invited collaborators** with interact-or-edit rights, not people holding
a public link. Public-link visitors get `null` from `user` and cannot write to `db`. For a handful
of classmates this is fine; it is not a "send it to anyone" product.

Also: `sample` calls are billed to the **viewer**, and consent is asked on first use.

### Cold start — onboarding a new user

A new user has zero labeled events. They are not stuck: the **shared prior** (§4 layer 2) already
knows that hands-on build nights convert and 200-person mixers don't. What it cannot compute
without them are the person-relative features. So onboarding collects exactly those, and no more.

**Four required questions.** Each one exists because a specific field cannot be computed without it:

| Question | Computes |
|---|---|
| Where do you live, and how do you get around? | `cost_blocks`, `reachable`, `go_if` |
| What are you optimizing for — role, industry, target companies? | `target_proximity` |
| What community are you already in (school, employer)? | `cohort_saturation` |
| How many evenings a week can you actually give this? | weekly quota |

**Two more, but do not put them in the form.** `phase` (building vs interviewing) can be asked
once in passing. The watchlist should **accumulate passively** from scanned speaker names — never
ask a new user to list thirty people they follow.

### End onboarding with the ranking exercise, not a settings screen

After the four questions, show **five real upcoming events** and ask: *which of these would you
actually go to?*

Three things at once: it produces `intent` labels on day one — the only personal signal that
exists before anyone has attended anything; it doubles as the hand-ranking calibration (which
Ashling herself never got around to doing); and it feels like the product working rather than a
form. The first session should end on a verdict, not a save button.

### Set the expectation: divergence is slow

Ashling's vision is that her scores and her friends' scores diverge as the system evolves. They
will — but **not in week one.** Week one, everyone gets shared prior + their own profile, so
scores differ only as much as their profiles do. Meaningful personal offsets need ~10 labeled
events, which at 2-4 events/week is a month or more.

Say this in the product. A user who expects personalization on day three and sees near-identical
scores concludes it's broken, when it is working exactly as designed.

### AMENDED 2026-09-21 — public link + sign-up is a requirement

She rejected the invited-collaborator constraint: *"I need it to run on public link with sign up to
be able to share."* That rules out the artifact runtime as the product surface. Artifact
capabilities are org-scoped by platform design — public-link visitors read as absent from `user`
and cannot write to `db`. Not configurable.

**Nothing in §1-§5 changes.** The schema, the freeze, the three layers, the shared/private
boundary, the onboarding flow — all of it is implementation-independent. Only the storage and
auth plumbing move.

**Target stack (smallest thing that satisfies the requirement):**

| Piece | Choice | Why |
|---|---|---|
| Frontend | Static page, Vercel/Netlify | Already designed; free tier |
| Auth | Supabase Auth (email / Google) | Public sign-up, ~an hour of work |
| Store | Supabase Postgres + **row-level security** | RLS maps directly onto §4: shared tables readable by all, `outcomes`/`contacts` restricted to `auth.uid()` |
| Pipeline | Existing local Python, pushes scored events up | Unchanged |
| Extraction | One serverless function holding the Anthropic key | The only genuinely new cost — see below |

**RLS is the thing that makes this work.** The §4 privacy boundary — pooled archetype stats shared,
contact notes private — is a row-level-security policy, not application logic. Same guarantee the
artifact `data/users/<id>/` subtree gave for free, now written down explicitly.

**The one cost that changes shape:** free-text extraction needs a server-side LLM call. On the
artifact route the *viewer* paid. On this route **Ashling pays for every friend's feedback
extraction.** Fine for five classmates; know it before inviting fifty. Mitigation if it matters:
ship light structure first and add extraction once there is usage.

**Two requirements that are being conflated — separate them:**

1. **Friends actually using it** → needs auth, DB, sign-up. Real project.
2. **Recruiters seeing it** → needs only a public, read-only page showing her own data and
   calibration story. Nearly free, and available immediately.

(2) does not depend on (1). Ship the read-only demo whenever the design lands; build the
multi-user app on its own timeline.

---

## §3b SCORING MODEL — segment revision, 2026-09-22

Not frozen (§3). Documented here rather than left in a prompt, because each rule below looks
arbitrary without its reason and will otherwise be "cleaned up" by a future agent.

**Trigger, not justification.** The Codex Community Meetup (lu.ma/5cewfkx1, 2026-09-22) scored
~0.17 and was skipped, when it was in fact a strong candidate. Each change below stands on its
own reasoning; none of the constants may be adjusted to make that event pass. Tuning to a single
data point is the failure `LESSONS.md` #13 exists to prevent.

### The bug: format was read from the title, not the agenda

"Codex Community Meetup" classified as `mixer`, which scores **0** on build — so S3 collapsed
despite the description stating: *"first 30 minutes hanging out and meeting people, then about
an hour of live demos."* A title is marketing copy. The agenda is usually in
`description_mirror`. **Classify from the described agenda.**

### Events have segments

One `format` enum cannot describe 30 minutes of social followed by 60 minutes of demos. It forces
a wrong answer either way, and averaging destroys the half that carried the value.

```
segments[]  { kind, duration_min, source }   source = described | inferred
```

Top-level `format` remains, as the dominant segment.

Segments pay for themselves twice: **the prep value-window falls out for free** (see
`PREP_SPEC.md` §1) — "30 min social, then 60 min demos" *is* the answer to when to arrive.

### Revised model

```
S3 = max over segments of FORMAT_S3_POINTS[kind] * min(1.0, duration_min / 45)
     gated by participant

S2 = TARGET_PROXIMITY_POINTS[target_proximity]
     * social_opportunity(segments)
     * COHORT_SATURATION_MULT[cohort_saturation]

value = (S3 + S2) * PRIOR_HOOK_MULT * COMPANIONS_MULT
p     = min(0.95, value / VALUE_TO_P_DIVISOR)
```

**S3 takes the max, not the sum.** Two demo blocks are not twice the inspiration.

### Why S2 is now gated on social opportunity

The previous model let contact value depend only on *who* is in the room. But **you cannot talk
to anyone during a lecture.** A talk attended by 384 target-company PMs with no mingle block
yields zero contacts. Proximity says who is there; segments say whether you can reach them.

```
social_opportunity = min(1.0, social_minutes / 45), FLOORED AT 0.25
```

**The 0.25 floor is not a fudge factor.** It is arrival, queue and departure, and it is the one
thing in this dataset we know from direct evidence: the entire payoff of the 2026-09-18 OpenRouter
event — meeting the Engineering 198 instructor, and the offer to take over the course — happened
**in the queue, before the doors opened**. See `LESSONS.md` #25. Do not remove this floor.

### Cohort saturation is S2-only

`cohort_saturation` was previously a global multiplier. That is wrong: a room full of her own
classmates does not make a demo less instructive. Apply it to S2 only — the same principle as the
sponsorship rule (§4): **a factor goes on the stream it actually affects, never globally.**

### Size: RETRACTED the same day it was written — record it, weight it ZERO

An earlier version of this section added `size_factor` (<=50 -> 1.0, 51-150 -> 0.7, >150 -> 0.4)
to S2. **Removed 2026-09-22, before it was ever built.** It was wrong, and how it was wrong is
worth keeping.

The evidence was two events, both fully confounded. Founder & Funder (200, zero contacts) also had
`wrong_ladder`, high cohort saturation, and spectator format — any of those explains the null.
Grok Bot (small, produced a contact and a tool) also had participant, `prior_hook = person`, zero
saturation, and a tier-1 host. Size was simply the variable that got named. A coefficient was
derived from n=2 with four confounds each — the exact error `LESSONS.md` #9 records, committed one
day after writing the rule against it.

Ashling's objections are stronger than that evidence:

1. **Small events are gated** — selective, hard to get into. A size penalty fights the `gated`
   field, which is meant to mark quality. The model cannot coherently reward selectivity and
   punish smallness.
2. **Good hosts draw crowds.** The Codex meetup is 384 people *because* WorkOS and Parallel put on
   something worth attending. Penalizing size penalizes host quality, backwards.

And structurally: everything size was assumed to proxy for is now modeled **directly** —
talk time is `social_opportunity`, composition is `target_proximity` + `cohort_saturation`,
structure is segments. Keeping size on top double-counts all three.

The one residual argument — competition for a specific speaker's attention — does not apply to
her. Her record shows she does not work speakers (no follow-up with Zara Zhang) and her contacts
come from ambient encounters. She met the Engineering 198 instructor **in a queue at a 384-person
event**.

So: `size` is recorded on every event and **weighted zero**, exactly like `host_tier`. It earns a
weight from outcomes or not at all.

**Open hypothesis, logged not encoded:** `gated` may be a *quality* signal (curated room, less
attention competition), not only the latency signal it is today. Needs support across >=3 events
before it touches the score.

### prior_hook becomes detectable

```
profiles.tools_used text[]   -- "products or tools you actually use", asked once at onboarding
```

Matched against event title/description -> `prior_hook = 'topic'`, with the matched term stored as
evidence. She uses Codex; the model had no way to know, and `prior_hook` defaulting to null is a
leading suspect in the 0.20-vs-0.60 miss on the OpenRouter event. This is the first of the three
un-scrapable fields to become scrapable.

### Re-scoring rules

`event_scores` is append-only, so re-scoring creates new rows — expected. Bump `model_version`.
**`outcomes.predicted_p_locked` is immutable** and the database trigger will reject any change to
it. A model revision must never be able to rewrite a prediction that was already recorded against
an outcome.

---

## §3c UNKNOWN IS NOT ZERO — 2026-10-01

Not frozen. But it is a direct extension of a frozen principle, and it must not be undone.

### The bug

`score/scorer.py`:

```python
s3 = FORMAT_S3_POINTS.get(row.get("format"), 0.0) if row.get("participant") else 0.0
s2 = TARGET_PROXIMITY_POINTS.get(row.get("target_proximity"), 0.0)
```

`.get(..., 0.0)` scores an **unknown** format identically to a **known-bad** one. A null
`participant` is falsy, so S3 also collapses. The model cannot distinguish *"this is a lecture for
VCs"* from *"we have no idea what this is."*

On 2026-10-01 that was **150 of 171 events** — all sitting at `predicted_p = 0.0` with a confident
`below_bar` verdict, when the honest statement was *"not enough information."*

### The principle, which is already ours

`SPEC.md` §1 (frozen): *unanswered = `unknown`, excluded from the fit, counted and displayed.*
*"Treating silence as 'no outcome' would teach the model everything fails."*

That was written for **outcomes**. It was never applied to **features**. It must be. Silence about
an event's format is not evidence the format is bad.

### Rules

1. **`null` and `0` are different values and must stay distinguishable** end to end — scorer,
   generated payload, UI.
2. **Unknown features score at a documented neutral prior**, not at zero. The prior is a stated
   constant, not computed from the currently-enriched sample: those 21 rows were hand-picked and
   are biased upward, so deriving a prior from them would bake that bias in. Replace with a real
   base rate once there is an unbiased sample.
3. **Every scored event carries `confidence`** = the fraction of scoring-relevant features that are
   actually known.
4. **Low confidence gets its own verdict, not a fake one.** Add `unscored` to the verdict set: *not
   enough information to judge*. It is a new enum value, which the §1 freeze rule permits (fields
   and values may be **added**; nothing existing is redefined).

   An event the model knows nothing about must never receive a confident `skip` **or** a confident
   `go`. Uncertainty cuts both ways.
5. **`unscored` is a queue, not a dead end.** Surfaced in the UI as its own group — *"12 events we
   don't know enough about yet"* — so missing data becomes something actionable rather than a
   silent mass of skips.

### Three-tier enrichment — no paid API required

The LLM pass is **tier 2 of 3**, not a prerequisite. Ashling declined metered API spend
2026-10-01; the system must work without it.

**Tier 1 — deterministic rules.** Most classification here is keyword work: *workshop, build night,
hackathon, demo, fireside, panel, mixer, office hours*. And §3b's rule — classify from the
described agenda, not the title — is largely parseable: *"first 30 minutes hanging out... then
about an hour of live demos"* yields segments with no model at all. Expected to cover the majority
of events deterministically, and deterministic beats probabilistic for something this mechanical.

**Tier 2 — a Claude session, not a metered API call.** ~30 new events a week is one paste. A
session reads the descriptions, classifies against this spec, and writes back to
`data/events.json`. Uses the subscription she already has, and a session applying the spec with
full context will outperform a terse API prompt.

**Tier 3 — metered API.** Optional, off by default. If a key is absent the pipeline must say so
loudly and exit non-zero — never continue silently leaving 93 rows null, which is what produced
this entire failure.

### Why this matters beyond the bug

A tool that renders `0.0 · below_bar` for an event it has never looked at is lying with a number.
It is the same failure as a calibration panel showing n=4 when only one row has a prediction, and
the same failure as a UI implying coverage it does not have. **Never display a confident value
derived from an absence.**

---

## §3d SLOT RANKING — PROPOSAL, NOT IMPLEMENTED — 2026-10-02

**Status: awaiting approval. `score/verdicts.py::_rank_key` still ranks by `predicted_p −
cost_blocks`. Nothing below has been built.**

### The bug

When more events clear `GO_BAR` than the week has slots, `verdicts.py` ranks them by
`predicted_p − cost_blocks`. The two terms do not share a unit: `predicted_p` is a probability in
[0, 0.95]; `cost_blocks` is a count of class/time blocks on the grid {0, 0.5, 1, 1.5, 2}. The
subtraction silently assumes **one block costs one whole unit of probability**, which no one chose.
Under that exchange rate a single half-block outweighs a 0.47 probability difference.

It also contradicts the rule the scorer states for itself (LESSONS.md #5, scorer.py's docstring):
*value and cost are separate axes; cost gates, it does not fold into the value number.*

### Evidence — real data, SF Tech Week (2026-W41)

With the week's slot budget at the standing default of 2, ranking by `p − cost`:

| event | p | cost | p − cost | outcome today |
|---|---|---|---|---|
| Agent Hackathon (Anthropic) | **0.80** | 1.5 | −0.70 | **quota_full — loses its slot** |
| Love at First Slide (Gamma × Atlassian) | 0.42 | 1.0 | −0.58 | GO |
| AI Heist Challenge | 0.67 | 1.0 | −0.33 | GO |

The highest-value event of the week loses to a 0.42 because it costs 0.5 more blocks. At a budget
of 3 or more the two rules produce identical verdicts on today's data, so this is a *scarce-slot*
defect: it bites exactly when the week is overbooked, which is when the ranking matters.

### Options

**A. Pick an exchange rate λ and rank by `p − λ·cost`.** Honest in form, but λ has no data behind
it: there are no outcomes yet that say what a block of her time is worth in probability. Any value
(0.1, 0.2, 0.3) is a made-up constant that will quietly decide the board. Rejected unless she
supplies λ from her own sense of what a block is worth — and then it should be a visible setting.

**B. Rank by value; let cost act only through the gates that already exist. (RECOMMENDED)**
Slot candidates are ordered by `predicted_p` alone, with `cost_blocks` (lower first) as the
tiebreak. Cost still does real work, but as a gate, not a number subtracted from a probability:
- `cost_blocks ≥ COST_DOWNGRADES_TO_PART (1.5)` still turns a won GO into PART (Pass 4);
- known-unreachable events still need top-3 value to become `go_if`;
- a confirmed RSVP still outranks everything.
This introduces **no new constant**, matches LESSONS.md #5 as written, and removes the unit error
rather than hiding it behind a coefficient. Its cost: two events of equal value never trade a
cheaper one against a slightly better one — a 0.60 event 2 blocks away beats a 0.58 event next
door. The tiebreak and the PART gate cover the extreme cases; the middle is a judgment call that
belongs to her, not to a fitted coefficient we cannot yet fit.

**C. Rank by value per cost, `p / (cost + k)`.** Removes the unit clash but needs `k` to avoid
division by zero at cost 0 — another unprincipled constant, and it over-rewards free events.
Rejected.

**D. Express cost in the same unit as value** (a block's opportunity cost = the P(hit) she would
earn from what she gives up in that block). The only fully principled option, and it needs
outcome data on the alternatives. Revisit once there are labelled events (SPEC.md §3, multi-user).

### What approval would change

Only `_rank_key` in `score/verdicts.py` (one function, one line of intent) plus its tests. Pass 4,
the `go_if` gate, conflict resolution and the confirmed-first rule are untouched.

### Decision needed

Approve B, or choose A and state λ. Until then the current ranking stays and this section is the
record that it is known to be wrong.
