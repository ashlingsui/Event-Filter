# Learning log — the session this project came out of

Raw material for writing, 2026-09-17/18. Distinct from `LESSONS.md`: that file holds the distilled
design principles. **This file holds the story** — what I actually thought at the start, what
changed, what I said in my own words, and the arguments I won.

---

## 1. Where I started

The original framing, in my own words:

> "There are so many different events on Luma, like SF Tech Week, hackathons... and they have
> various quality. I live in Berkeley, and I don't drive... When I don't do those filters correctly,
> I feel like I need to be at everything, and it creates a lot of fear of missing out. I want to
> build a filtering system for myself so that I know, 'Okay, don't worry about it. When you don't
> attend this event, it's fine because it doesn't fit your goal or your purpose.'"

> "The incremental value of going so far away to this event is low."

> "I want to develop a scientific system to actually calculate it."

I thought I was describing a filtering problem. The first thing that got pushed back on was that
framing — it's a **permission problem**. A scoring rubric still leaves you doing math on every
listing, and the anxiety was never that the math was wrong. It was that there was no pre-committed
rule, so every event reopened the question.

That reframe changed the whole design: the system needed a *quota* and a *counterfactual*, not
just a score.

---

## 2. The arc, in order

| Stage | What changed |
|---|---|
| Filtering → permission | The anxiety isn't about picking wrong. It's about having no rule. |
| Score → counterfactual | An event competes against the best alternative use of that block — usually a coffee chat with an alum — not against zero. |
| Score → probability | A 7.2/10 can't be checked. `P(this produces an outcome)` can be, against what actually happened. |
| Hours → deep-work blocks | A 6pm SF event doesn't cost 4 hours. It costs the day's maker block. |
| Breadth → depth | Ten one-off events = ten cold weak ties. Four visits to one community = relationships. FOMO pushes exactly the wrong way. |
| Events → people | Watching a list of ~30 people is higher-precision than scoring every event that appears. |
| Predict → calibrate | The output isn't a ranking. It's the **gap between what felt valuable and what delivered.** |

---

## 3. The four times I corrected the model — and why I was right

This is probably the most interesting thread in the whole session. Each time, the model
generalized and I had context it didn't.

### (a) The friend paradox

It argued that bringing classmates makes you less likely to meet new people, citing my 200-person
Haas event where I met nobody new.

What I said:

> "I love going with friend, that means you can talk about it later and review the outcome
> together, I am also less nervous when I go with a friend, I always meet new people, the only
> reason why I didn't meet too many new people is because the whole crowd was basically our class."

Two variables were tangled: companionship and **cohort saturation**. The room being my own class
was the problem. Going with a friend is a *positive* — I'm more likely to go at all, and the
debrief afterward is how I extract the value.

### (b) "You could get that online"

Twice the model discounted an event because the content was available online — first the opinions,
then the demos.

> "Sometimes I am lazy, I don't get those opinion online."

> "Grok bot was great because I saw amazing demos (demos I might be able to access online but I
> would not do so normally)."

The counterfactual isn't the podcast. It's **nothing**. In-person is a commitment device. That
discount got struck from the model entirely.

### (c) "Peers can't help you"

It argued that a room of peers is a room of people competing for my jobs.

> "MBA second yrs can refer me, they have connections of places they have worked before, the
> evening weekend part time MBAs might be working at the places where I want to go."

**"Haas student" is not a career position.** My EWMBA/EMBA classmates currently work at my target
companies. The feature isn't seniority — it's *target proximity*. Which produced the rule I can act
on immediately: EWMBA/EMBA events are networking events, full-time cohort events are social events.

### (d) T+14 was too long

> "T+0 or T+1 are easy for me to register thinking, and T+7 for yes no question, because I have
> bad memory."

That didn't just shorten a timer. It changed the question *type* — from recall ("who did you
meet?") to recognition ("any of these five people?"). Designing around the memory I actually have
rather than the one I wish I had.

**The pattern:** every correction was a case where my specific situation beat a reasonable general
principle. All four general principles were defensible. All four were wrong for me.

---

## 4. Method I'd reuse

- **Spec only what's expensive to change.** The whole spec is one page and it pins exactly one
  thing: the definition of an outcome. Weights, UI, calendar list — all deliberately left open,
  because they're cheap and better decided against data.
- **Freeze the label, then let everything else evolve.** A learning system needs a stationary
  target. The freeze isn't in tension with "self-evolving" — it's the precondition.
- **Make the prediction before the event, in writing, and never edit it.** Four predictions are
  locked in `BUILD_HANDOFF.md` with reasoning. That record can't be reconstructed later.
- **Start collecting before the tool exists.** Outcomes accrue on calendar time, not build time.
  First prediction was made by hand in chat the day before an event — n=1 the next day instead of
  in three weeks.
- **Grill the frozen parts, not the reversible ones.** We interrogated the outcome taxonomy for a
  long time and spent almost no time on the UI. Correct allocation.
- **Build exploration in deliberately.** A system that only sees the events you attended becomes
  self-confirming. ~1 in 7 has to be a wildcard or the model just gets more confident while getting
  worse.

---

## 5. What I learned about my own behavior

- My favorite event and my two duds are explained by one question: **was I a participant, or was I
  watching someone else's event?** Both duds were VC/founder-ecosystem events. I am neither.
- Every event I felt good about, I arrived with a hook — I'd been following the speaker, or I
  already used the product. Every dud, I showed up cold.
- Founder & Funder Night felt *amazing* and delivered nothing. I described it as: "it was fun, the
  food and drinks were great." That gap is the thing worth measuring.
- The highest-value events on my calendar have **zero commute** — the startup class with 8 speakers
  from OpenAI, Stripe, and Waymo, where I'm an experienced MBA in a room of undergrads. I almost
  didn't mention it because it didn't feel like "the SF tech scene."
- Without a car, my real cost structure isn't distance — it's whether an event sits on a path I'm
  already taking. The OpenRouter event costs me nothing because a friend is driving and it's on the
  way to Yosemite.
- I said this myself early on, and it turned out to be the load-bearing insight: *"meeting the best
  AI founder, you don't meet them through those events."*

---

## 6. Candidate blog angles

**(a) "The four times I corrected the AI."** ← strongest, and most differentiated
Each correction was a case where my specific context beat a sound general principle. For an AI PM
portfolio this demonstrates the exact skill the job is about: knowing when to override the model.
Section 3 is already the outline.

**(b) "I built a system to give myself permission to skip things."**
The FOMO angle. Broadest appeal, least technical. Thesis: the problem was never picking correctly,
it was the absence of a pre-committed rule.

**(c) "Spec what's expensive to change."**
PM craft. Short, opinionated, recruiter-friendly. Thesis: a PRD's value is entirely in the
irreversible decisions; everything else should be prototyped.

**(d) "Felt value vs. delivered value."**
The measurement angle. Thesis: the useful output of a personal scoring system isn't the score, it's
discovering which experiences reliably fool you in the moment.

---

## 7. Open questions I still hold

- Is `prior_hook` a feature or an intervention? If prep manufactures it, does scoring it beforehand
  contaminate the label?
- Does the system survive November, when recruiting peaks and logging feels like a chore?
- Will the calibration panel have enough rows to say anything honest by the time I'd want to show
  it to someone?

---

## 8. My answers — the reflective material

### Who this is for

Recruiters reading my portfolio, so they can see I've done a serious stretch of work *with* AI —
and networking contacts, so they see something beyond the resume.

That settles the angle: **show the working, not the conclusion.** The interesting artifact isn't
the tool, it's the reasoning trail — including the parts where I overrode the model.

### What surprised me most

The **wildcard design**. How do you make a system that evolves per user without naively going down
a narrow rabbit hole? I hadn't thought about the fact that a system which only sees what you *did*
never learns what it cost you to skip — so it gets more confident while getting worse. The fix —
deliberately attending something the model rated low, roughly one in seven — is both a statistics
fix and, weirdly, a permission slip.

### What I believed at the start that I no longer believe

I thought this was **an easy weight calculation model**. Score the event, sum it up, done.

Two things broke that.

First: **preparing the hook matters more than the score.** Every event I felt good about, I arrived
with something specific to say. The ranking picks the room; the prep is what makes the room worth
being in. That inverts what the product actually is.

Second — and this is the one I'll write about: **the way I described each event revealed how much I
valued it, and none of that was standardized.** "It was fun, the food and drinks were great" versus
"I've been experimenting with it since day one" — those aren't the same sentence at all, and no
dropdown would have captured the difference. The unstructured descriptions carried more signal than
any form would have. Collecting my own past events, in my own messy words, turned out to be the
highest-value step in the whole journey.

*Design consequence:* never replace the free text with a form. Capture the sentence, let the model
extract. (My `TRACKER.md` already said this a month ago — "Chat is the input. Do not build forms."
I apparently had to learn it twice.)

### Does the FOMO feel different already?

**No. It's still there, hanging.**

Worth being honest about, because it's diagnostic. The reframe gave me *reasons* to skip. It didn't
give me a *rule* that skips. Reasons argue with you; rules decide for you — and nothing has decided
anything yet, because the quota isn't set and no system has told me "no" out loud.

Which means the output can't be a ranked list. A ranked list leaves the decision open, and an open
decision is exactly what the anxiety feeds on. It has to be a **verdict with a reason attached.**

### What was hardest to admit

That I have to be authentic to get an accurate result — and that being authentic is sometimes
easier with an AI than with a person. The unflattering answers are the load-bearing ones here: I
don't watch the content online, my memory is bad, I went to that event partly for the food and my
classmates. A system built on the flattering version of me would have produced a flattering,
useless model.

### Anything I disagreed with but didn't say

I disagree all the time — and running `grill-me` brought out the devil's advocate in me too. Being
interrogated made me argue back harder and sharper than being agreed with ever did.
