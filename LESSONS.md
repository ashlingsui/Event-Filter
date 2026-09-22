# Lessons — building the Event Filter

Running notes for the learning blog. Each one has the incident attached, because the incident is
what makes it worth reading. Started 2026-09-17.

---

## 1. Spec what's expensive to change. Prototype everything else.

I asked whether we needed a PRD. The answer was no — but not because specs are bad. Because for
this project almost *nothing* was expensive to change: weights, UI, the calendar list, the scoring
formula are all cheap and are better decided against real data.

Exactly one thing was expensive: **the definition of an outcome.** That's the label. Redefine it
three weeks in and every row collected before the change becomes inconsistent, and the calibration
record — the only part of the project that's hard to fake — is destroyed.

So the spec is half a page, and it pins the label and nothing else.

> Write down the decisions where being wrong is expensive to undo. Everything else, build and find out.

---

## 2. A metric that fires on everything measures nothing.

My first outcome definition was `hit = POV OR contact OR build`. Meeting a Google PM who later
refers me = 1 hit. Hearing an opinion I repeated once at lunch = also 1 hit.

An OR across unequal outcomes flattens them. Worse: a model trained to predict `hit` will learn to
chase whichever outcome type is most **frequent**, not most **valuable**. That's how a scoring
system quietly starts optimizing for the cheap thing.

---

## 3. The softest label wins, and that's a problem.

Of my three outcome types, "did I hear an opinion that changed my mind" is self-assessed and
essentially unfalsifiable. Events reliably *feel* educational. So that label would fire on most
events, and since `hit` was an OR, nearly everything would score as a hit — and a model where
everything is a hit tells you nothing.

The test I now apply: **can this label be proven false?** If not, it isn't a label, it's a feeling.
The falsifiable version: *I can name the specific claim, and it appears in writing within 14 days.*

---

## 4. Felt value ≠ delivered value. The gap is the whole product.

Haas Founder & Funder Night felt *amazing* — great food, first startup event with classmates — and
produced zero connections. The a16z build night felt good AND produced a tool I still use plus a
real contact.

So I capture two separate labels: a **felt score the same night**, and a **factual outcome check at
T+7** (with a batch sweep at T+30 for anything still open). The gap between them, sorted by event
type, is the most useful output of the system —
because learning that mixers reliably feel great and deliver nothing is exactly what makes skipping
the next one feel safe instead of anxious.

> The point isn't to predict well. It's to find out where my gut is systematically wrong.

---

## 5. Keep value and cost in separate columns.

The OpenRouter event: I'm going Friday (no class), a friend is driving, and it's on the way to
Yosemite. Cost went to roughly zero.

The temptation is to say "so it's a better event now." It isn't. **Cost collapsing changes the
decision, not the probability of a good outcome.** P(hit) actually went slightly *down*, because
leaving for Yosemite means no lingering afterward, and the post-event mingle is where contacts form.

Conflating the two corrupts both numbers.

---

## 6. Score against the counterfactual, not against zero.

The alternative to a Thursday SF event isn't staying home — it's a coffee chat with a Haas alum who
is already a PM at the company I want. An event only earns the slot if it beats the best
alternative use of that same block.

Most don't. And they lose on rigorous grounds, which is very different from losing on vibes.

---

## 7. No leakage: features must be knowable *before* the decision.

Obvious once said, easy to violate. If a field can only be filled in after the event, the model
can't use it at prediction time. So the schema is split hard: pre-event fields vs. post-event
fields, with `predicted_p` recorded before and **never edited after**.

---

## 8. Ask: am I the participant, or am I watching someone else's event?

The single filter that retroactively explained my first three outcomes. My two duds — Founder &
Funder Night, Venture Math on SAFEs — were VC/founder-ecosystem events where I was a spectator. My
one hit was a *build night*, and I'm a builder.

Not "is this event good." **Is this event for someone like me.**

---

## 9. One data point can't separate confounded variables.

Claude proposed a "friend paradox": bringing classmates makes you less likely to meet new people,
citing my 200-person Haas event where I met nobody new.

Wrong — two variables were tangled. The problem wasn't that I brought friends, it was that **the
whole room was my own class**. Cohort saturation, not companionship. Going with a friend is a
*positive*: I'm less nervous, more likely to actually go, and we debrief afterward.

> When a single example "proves" a theory, check what else was true about that example.

---

## 10. Data collection has a lead time that code does not.

Outcomes accrue on calendar time. Waiting for the tool to be finished before logging anything would
cost weeks of data for no reason. So the first prediction was made by hand, in chat, the day before
an event — n=1 the next day instead of in three weeks.

---

## 11. Don't let the UI imply completeness it doesn't have.

Luma has no global search. Coverage is exactly the union of the calendars I follow. So the interface
has to say "everything on your calendars," never "everything" — and carry a discovery strip for
calendars worth adding.

Overstating recall is how a tool teaches you to trust it wrongly.

---

## 12. The prep is the product, not the score.

Every event I felt good about, I arrived with something specific to say — I'd been following the
speaker, or already used the product. Every dud, I showed up cold.

Scoring picks the room. **A prior hook is what makes the room warm.** And a hook can be manufactured
in twenty minutes of prep, which means the highest-leverage feature isn't the ranking — it's the
brief.

---

## 13. Small n is a design constraint, not a limitation to apologize for.

I'll hand-rank 5-10 events. That supports roughly 4 fitted parameters before it's fitting noise. So
the model *has* to stay small — which also makes it interpretable and debuggable.

~~Still open: at 2-4 events a week, is fitting weights science or theater?~~ **Resolved — see #17.**

---

## 14. Design around the memory you actually have, not the one you wish you had.

The first outcome check was T+14, and I said plainly: my memory is bad, that won't work. The fix
wasn't discipline. It was changing the *question type*.

> **Recognition beats recall.** Never ask "who did you meet?" Show the scraped speaker names and
> the contacts I logged, and ask "any of these?"

Recall fails in two weeks. Recognition survives. Same data, a fraction of the effort — and the
answers are more accurate, because I'm reading a list instead of reconstructing an evening.

Most systems that die of neglect die at the data-entry step. That step is a design problem, not a
willpower problem.

---

## 15. "Peers can't help you" is a category error.

Claude argued that a room full of peers is a room full of people competing for my jobs, so
networking events full of classmates can't produce referrals.

Wrong, and wrong in an interesting way: **"Haas student" is not a career position.** My EWMBA and
EMBA classmates *currently work* at the companies I'm targeting. A second-year has already interned
at one. The room looks homogeneous by affiliation and isn't, at all.

So the feature isn't seniority or peer-ness. It's **target proximity** — how many people here are
currently inside the places I want to be. Which produces a rule I can act on immediately:

> EWMBA/EMBA events are networking events. Full-time cohort events are social events. Same school,
> same building, completely different value.

No rubric that treats "Haas event" as one category will ever see that.

---

## 16. "You could get that online" is a fictional discount.

Twice the model tried to talk me out of an event because the content was available online — the
opinions, and then the demos.

But I don't watch the recap. I don't listen to the podcast. I consume what I *attend*, and I
bookmark what I don't. So the counterfactual isn't "the podcast," it's **nothing**.

> In-person is a commitment device. That's a real mechanism, not a rationalization.

Struck from the model entirely. It's the most common way a rational-looking system argues you out
of something that actually works for you.

---

## 17. A system that only sees what you did becomes self-confirming.

If the model says skip, and I skip, it never finds out it was wrong. Feedback only ever arrives for
events I attended — so a "self-evolving" system quietly narrows onto whatever it already believes,
growing *more* confident while getting *worse*.

The fix is deliberate exploration: **roughly one in seven events is a wildcard** — something the
model scored low, attended anyway, flagged as exploration. It's the only way the thing can discover
it's wrong.

Nice side effect: it makes going to something random *part of the system* rather than a failure of
discipline. The wildcard slot is a FOMO feature and a statistics feature at the same time.

And the answer to #13: fitting weights on one person's 2-4 events a week really is theater. Across
many users it isn't — you pool a shared prior over event archetypes and learn a small personal
offset on top. Cold-start is solved by other people's data, not more of mine.

---

## 18. You can only evolve against a fixed target.

I asked whether locking the spec now would get in the way of building a system that learns as it
goes. It's the opposite: **the freeze is the precondition.**

A learning system needs a stationary label. If the definition of "this event was worth it" drifts
while data accumulates, nothing can learn — you get noise that looks like progress, and a
calibration chart that means nothing.

So: freeze the label, version every row, and let everything else move.

> Lock the target. Evolve the aim.

---

## 19. The unstructured description carried the signal. A form would have destroyed it.

The single highest-value step in this whole project was describing my own past events in my own
messy words. Not filling in fields — talking.

"It was fun, the food and drinks were great" and "I've been experimenting with it since day one"
are not the same sentence. One is cohort value, one is a build outcome. No dropdown would have
separated them, because I'd have ticked "interesting" for both.

> Capture the sentence. Let the model extract. Never make yourself fill in a form about your own
> experience — the phrasing *is* the data.

My own `TRACKER.md` already said this a month ago: *"Chat is the input. Do not build forms."*
Apparently I had to learn it twice.

---

## 20. Reasons argue with you. Rules decide for you.

Honest check at the end of the design session: does the FOMO feel different yet?

No. Still hanging there.

That's diagnostic, not disappointing. Everything so far produced *reasons* to skip — good ones,
grounded in my own data. But a reason is something you can negotiate with at 11pm while looking at
a Luma page. A rule isn't. And nothing has actually decided anything yet: the quota isn't set, the
wildcard isn't running, and no system has told me "no" out loud.

> Understanding why you're allowed to skip something is not the same as having something skip it
> for you.

**Design consequence:** the output cannot be a ranked list. A ranked list leaves the decision open,
and an open decision is exactly what the anxiety feeds on. The system has to return a **verdict
with a reason attached** — go, skip, or go-for-this-part — and it has to say it first, before I've
had a chance to negotiate.

---

## 21. The system only works on the unflattering version of you.

The load-bearing inputs in this design were all admissions: I don't actually watch the content
online. My memory is bad. I went to that event partly for the food and because my classmates were
going.

Every one of those changed a design decision. A model built on the version of me I'd put in a cover
letter would have been polite, plausible, and useless.

> Any self-measurement system is only as good as your willingness to be unflattering in the input.

---

## 22. A status bar should show what you'd act on, not what the system is proud of.

My first dashboard header read: *scanned 31 · cleared filters 6 · calendars 8 · wildcard 1 of 7*.

I looked at it and said those numbers don't mean anything to me. They didn't. Every one of them
was the system reporting on its own effort — impressive-sounding, actionable by nobody.

What replaced them: slots left this week, next commitment, which RSVP closes soonest, how many
outcome checks I owe. Four things I would actually *do* something about.

> Top-of-page real estate goes to decisions, not to throughput metrics. If a number doesn't change
> what you do next, it's decoration.

Same test applies to the sidebar: a nav rail on a four-section page is furniture. It earned its
place only once it carried state — *1 check due*, *2 briefs ready*. Navigation is not a feature;
a standing to-do signal is.

---

## 23. Convening power is invisible to a proximity score.

The most valuable person I met at the OpenRouter event was a Berkeley junior. He works at none of
my target companies. He's younger and more junior than I am. Every feature in my schema would
score him near zero — `target_proximity` measures how many people in a room work *at* the places
I want to go.

But he instructs Engineering 198, and all eight of its speakers — Stripe go-to-market, a Waymo PM
lead, OpenRouter — come from his own personal network. And he offered that Ivy and I could take
over the course next year.

> Some people are valuable for the position they hold. Others are valuable for the rooms they can
> *create*. A density-of-seniority feature only sees the first kind.

The second kind is worth more to me right now, and I have no way to score it. Worth sitting with:
the best outcome of the project so far came from a variable the model cannot represent.

And note where I found him — at an SF event, about a Berkeley asset. The neat rule I'd written
("campus serves S1 and S4, trips must clear S2 or S3") held, but not in the direction I expected.

---

## 24. One vivid outcome is not a policy change.

Walking out of a good event I said: *the fact that it's in SF doesn't matter that much, I'm
willing to go to events in SF.*

That's an n=1 update from the most memorable data point available, which is exactly the bias the
whole system exists to correct. And the trip cost me **zero** — Friday, no class, a friend driving,
on the way to Yosemite. Would I read it the same way if it had cost a class skip?

The honest update is narrower than the one I wanted to make: *participant-ish SF events carry more
unmodeled upside than I'd credited.* Not: *distance stopped mattering.*

> The point of writing the prediction down first is to stop a good night from rewriting the policy.

---

## 25. The value happened in the queue, before the doors opened.

The best thing that came out of the OpenRouter event — meeting the Engineering 198 instructor,
and the offer to take over the course — happened **outside, while waiting to get in.** The event
had not started. Nobody had spoken. No slide had been shown.

Sit with what that does to the model. Every feature I score describes what happens *inside* an
event: format, participant-or-spectator, who's in the room, size, host. The entire payoff of my
first real data point occurred before a single one of them applied.

So what actually produced it? The event's **draw** — who self-selects to stand in line outside an
OpenRouter × a16z event in San Francisco on a Friday. The program was incidental. The event
functioned as a gathering point for a certain kind of person, and I happened to be standing next
to one of them.

> An event is not a program you attend. It is a filter on who else shows up.

Two things follow. One: **arrival time is a lever**, not a logistic. The pre-event window is not
dead time before the value starts — for me, it *was* the value. Two: I should be asking "who does
this event attract?" at least as hard as "what happens at it?" — and those can have completely
different answers.

The uncomfortable part: I can't score this yet. Draw isn't in my schema, and I'm not sure it's
scrapeable. Logged as a hypothesis rather than a feature.

---

## 26. The prep advice was right, and for the right reason.

Pre-event, the brief said: *hard stop at 14:00, so there's no post-event mingle — get there early
and work the room before it starts.*

That is precisely where the entire payoff came from. Not a lucky guess about a venue — a
prediction about *where in the evening the value would be*, made from the event's shape, and it
held on the first real test.

Confirms #12 on live data: scoring picks the room, but the brief is what converts it. If I had
shown up at 12:00 sharp I would have met nobody.

---

## 27. I wrote the rule, then broke it the next day.

Lesson #13 says: at my sample size, fitting coefficients is theater. Lesson #9 says: when one
example "proves" a theory, check what else was true about that example.

Then I added a three-bucket size penalty to the scoring model on the strength of **two events**.

Founder & Funder: 200 people, zero contacts. Grok Bot: small, produced a contact and a tool I
still use. Looks like size. But the first was *also* a VC/founder room, *also* full of my own
class, *also* an event I was a spectator at. The second was *also* hands-on, *also* an event I
arrived at with a hook, *also* hosted by a16z. Four confounds each. Size was just the variable I
happened to name out loud.

What caught it wasn't the framework. It was asking a plain question: *how much does size actually
matter to me?* — and noticing two things the model couldn't see. Small events are small because
they're **gated**, so penalizing size fights the field that marks selectivity. And good hosts draw
crowds, so penalizing size penalizes host quality.

> A rule you wrote does not protect you from the error it describes. Nothing does, except someone
> asking whether the number is real.

The structural tell, once I looked: everything size was supposedly proxying for — talk time, room
composition, event structure — had *already* been modeled directly. The new coefficient wasn't
adding information, it was triple-counting information the model already had.

Size is now recorded and weighted zero, like host prestige. It earns a weight from outcomes or it
doesn't get one.
