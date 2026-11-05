---
name: start-change
description: Use this first, before planning, designing or writing any change to production code (a fix, a behaviour change, a new feature, a new job or service, a refactor), including in plan mode and when asked to "plan this", "design this", "take this issue", "where does this fit" or "how big is this". It routes the work to the right amount of design — trivial (no document), small (one spec-and-tasks document, change-design) or full (system design then implementation plan, feature-design) — by reading the issue and the code for the deciding signals (projects touched, size, migrations, contracts and their consumers, consumers and jobs, boundaries, auth), proposing a track in one line and letting the person override.
---

# Start a change: pick the track

Every change to production code goes through one of three tracks. This skill picks one, says why
and hands off. It writes nothing itself.

| Track | What you get | Skill |
|---|---|---|
| **trivial** | no document; a trivial branch and an issue reference | none |
| **small** | `features/<N>-<slug>/change.md`: spec, tasks, verification; one review, one approval | `change-design` |
| **full** | `design.md` then `plan.md`, diagrams, caveat packs, two reviews, two approvals | `feature-design` |

All three keep the same rule: no code without knowing what the change does, how we'll know it
works and what it must not break. The tracks differ in how much is written down to prove it.

## Procedure

1. **Profile.** Read `.claude/profiles/feature-workflow.md`. If it is missing, set it up as the
   `feature-design` skill describes (*Project profile*), then come back. Its *Tracks* section may
   change the thresholds and triggers below; the profile wins.
2. **Issue.** Read the issue with its comments, or draft one, exactly as `feature-design` Stage 0
   describes. Trivial work still needs an issue reference.
3. **Signals, from the code.** Do not route from the chat alone. Find the code the change lands in
   and check, briefly:
   - which projects or deployables it touches (named as the profile's source names them);
   - roughly how many lines change;
   - each full-track trigger below: grep the callers of the types, routes and messages you would
     change, look at the migrations folder, the contracts and who consumes them, the consumers and
     jobs near the change, the auth policies on the entry point.
4. **Propose.** One line: the track and the signal that decided it, then ask for an override.
   - `Track: small — Orders.Api only, ~150 lines, no contract, migration or consumer change. OK, or trivial/full?`
   - `Track: full — adds a column to orders (migration) and a field to OrderPlaced, consumed by Billing. OK?`
5. **Hand off.**
   - trivial → branch per the profile (default `trivial/<slug>`), fix test first, no document.
   - small → follow the `change-design` skill.
   - full → follow the `feature-design` skill from Stage 1 (the issue is already read).

In plan mode, routing happens inside plan mode; the document the chosen track produces is the plan.

## Routing rules (defaults)

**Full** if any of these is true:

- a schema change or migration;
- an API, message, event or generated client that another team or deployable consumes changes in a
  way a consumer must react to: a removed or renamed field, a new required field, a changed meaning,
  or a regenerated client that others must pick up (an optional parameter on an endpoint only your
  own app calls is not a trigger);
- a new or changed consumer, background job, saga or loop;
- data or behaviour crosses a bounded-context or team boundary in a new way;
- more than two deployables change;
- a new external dependency (service, SaaS, model, store);
- an authorisation, tenancy or data-retention change;
- a new user-visible flow of more than one step.

**Trivial** if all of these are true: under the profile's trivial threshold (default ≤ 100 changed
lines in ≤ 2 projects), an issue is referenced, and it adds no new behaviour: it corrects or tidies
behaviour that already exists (a typo, a wrong default, an off-by-one, a log line).

**Small**: everything else, typically a behaviour change contained in one or two projects behind an
existing contract (a validation rule, a filter on an existing list, a field shown that is already
returned, a tweak to an existing handler's logic).

If the person overrides to a smaller track despite a trigger, accept it, and let the chosen skill
record the override so it is not raised again.

**Unsure between two tracks, pick the larger.** A small change can be promoted to full later
(`change-design` describes how); a trivial change that turns out to change behaviour is restarted as small.
