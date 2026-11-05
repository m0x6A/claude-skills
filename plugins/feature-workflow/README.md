# feature-workflow

No code without a written spec, at the size the change deserves. Every change answers four
questions before code: *what it does*, *how we'll know it works*, *what it must not break* and
*how we'd debug it at 3 am* (if you were on call and it broke, what observability would you need?).
How much gets written down to prove that depends on the track.

## Tracks

`start-change` reads the issue and the code, proposes a track in one line with the signal that
decided it, and lets you override:

| Track | When | What you get |
|---|---|---|
| **trivial** | under the profile's threshold (default ≤ 100 lines, ≤ 2 projects), no behaviour change beyond the fix | a trivial branch, no document |
| **small** | a contained behaviour change behind existing contracts | `change-design`: one `change.md`, one light review, one approval |
| **full** | a migration, a consumed contract change, a new consumer or job, a boundary crossing, > 2 deployables, a new dependency, an auth change, a new multi-step flow | `feature-design`: `design.md` then `plan.md`, two reviews, two approvals |

Unsure → the larger track. A small change that turns out to hit a full trigger is promoted, keeping
its problem and spec.

## Small track: `change-design`

`features/<N>-<slug>/change.md` holds the spec (S1…, the evidence for each, N1… with its guard), where
it changes, a one-line-per-row triage of the core caveats, test-first tasks tied to spec items, and
verification. The `design-reviewer` agent (`STAGE=small`) checks the spec and whether the change really
is small, with at most three findings.

## Full track: `feature-design`

Takes a feature from an issue to two documents in `features/<N>-<slug>/`, each reviewed by the
`design-reviewer` agent and approved by a person before the next step:

1. **design.md** opens with the spec: *what the change does* (S1, S2, …), *how we'll know it works*
   (the evidence for each statement), and *what it must not break* (N1, N2, …, each with its guard), and *how we'd debug it at 3 am* (O1, O2, …: failure, how we find out, the
   signal that localises it, the first action). Then
   the system map with affected parts highlighted, sequence, control-flow, data-flow, ER and state
   diagrams, affected parts, a caveats checklist (a core list plus messaging, gateway, web, data and AI
   packs), concurrency and idempotency tables, and numbered decisions.
2. **plan.md** lists ordered, test-first tasks, each tied to spec items, and a verification section that
   proves every "works", "must not break" and "3 am" row.

The reviewer leads with a spec check, a ranked risk map and the problematic patterns it sees
(`references/patterns.md`), then at most seven findings, checked against the real code.

## Setup

On first use the skills create `.claude/profiles/feature-workflow.md` with you (layout, tracker,
tracks and their thresholds, deployables, caveat packs, rules) and a `system-base.mmd` diagram of your
system. It uses `gh` for GitHub issues by default.
