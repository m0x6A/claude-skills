---
name: change-design
description: Use whenever someone asks for a quick spec, a small or lightweight design, a short plan, "spec and tasks", or says a change does not need the full design ritual, and whenever start-change routes work to the small track. The small track of the feature workflow: for a contained behaviour change (one or two projects, behind existing contracts, no migration, no new consumer) write one short change.md holding the spec (what the change does, how we'll know it works, what it must not break, what on-call would need to debug it at 3 am), where it changes, a core-caveats triage, test-first tasks and verification; a light design-reviewer pass; one approval by a person before code. Escalates to feature-design when a migration, contract change, consumer or boundary crossing turns up.
---

# Change design: the small track

One document, one review, one approval. It keeps what makes the full design worth doing (a spec
someone else can check, tasks that each serve it, and verification that proves it) and drops the
ritual that only pays off for larger work: the diagrams, the full caveat packs, the concurrency
tables, the separate plan and the second gate.

**The spec is not optional here either.** If you cannot say what the change does, how we'll know it
works, what it must not break and what on-call would need to debug it at 3 am, ask the user. Do not write a vague answer.

## Before you start

The issue is read and the profile loaded (by `start-change`, or as the `feature-design` skill
describes in *Project profile* and *Stage 0*). Feature id `<N>-<slug>`, same as the full track.

## Write `<features>/<N>-<slug>/change.md`

Start from `templates/change.md`. Its §1 and §2 have the same headings, numbering and table
columns as a full design, so a promotion copies them unchanged. Rules per section:

- **Frontmatter**: fill every key, as for a full design (`produced_by.model` is the model id you run
  as, `author` the git user, `review` on one line in flow style). `track: small`. `status` stays
  `proposed` until a person approves.
- **§1 Problem**: condensed from the issue; acceptance criteria verbatim, numbered AC1, AC2, … so §2
  can cite them. One line of prior art if Stage 0 found any.
- **§2 Spec**:
  - *2.1 Does* (S1, S2, …): behaviour from the outside, "When <actor> <does>, <observable result>".
    Every acceptance criterion is covered by an S-statement.
  - *2.2 We'll know it works*: one row per S-statement and acceptance criterion; prefer a named test.
  - *2.3 Must not break* (N1, N2, …): read the code to find the neighbours: the callers of what you
    change, the screens and flows next to it, the guarantees in specs and ADRs. Each gets a guard:
    an existing test you opened and confirmed exercises it, or a new one. "Nothing" is not an answer.
  - *2.4 Debug at 3 am* (O1, O2, …): if you were on call at 3 am and this broke, what would you
    need to solve it? For each realistic failure mode of the change: how we find out, the signal that
    localises it (log line with its ids, metric, span) and the first action. Often the existing
    telemetry already covers it: then name the existing signal and say you checked it fires on this
    path. A missing signal becomes a task. Usually one or two rows.
- **§3 Where it changes**: one line per project and file. No diagrams by default; add one Mermaid
  `sequenceDiagram` only if the flow is not obvious from the list (labels on one line, `·` between parts).
- **§4 Caveats triage**: the *Core* rows of `../feature-design/references/caveats.md` plus the rows of
  each pack the profile enables, plus the profile's own rows. Open the thing in "Look at" before
  answering. Write a line for each row that applies; collect the rest on one line,
  `n/a: <row>, <row>, … — <shared reason>`, so the triage costs what the change deserves. A caveat
  that shows a neighbour at risk adds an N-row to §2.3. One that hits a full-track trigger (see
  `start-change`) means **escalate** (below).
- **§5 Tasks**: ordered; each names its test, the files, and the S/N/O items it serves. A test for an
  S-item must fail today (say why). A new guard for an N-item may pass today; it pins existing
  behaviour so the change cannot move it, so say what it pins. A task that serves no S/N/O item is
  scope creep: cut it, or add the item to §2.
- **§6 Verification**: the exact commands to run and any manual check to walk. No restated table:
  §2 says what proves each item, §5 says which task produces it. The PR is ready when every task is
  ticked and these pass.
- **§7 Decisions**: only if there was a real choice: decision · why · rejected alternative. A
  decision that sets a rule for other features means escalate (it needs an ADR). An accepted
  override of the router also goes here (see *Escalate to full*).

## Review, gate, build

1. **Review.** Run the `design-reviewer` agent with
   `STAGE=small. Review <features>/<N>-<slug>/change.md for issue #<N>.` It returns a spec check, a
   track check and at most three findings. Copy the spec check and track check into **Review
   outcome**. Fix what you agree with; for one you keep, write `Accepted: <finding> — <reason>`.
   Re-run only if there were blockers. Set `review.small` to `passed` or `accepted-risks` with the date.
2. **Gate.** One short message: the spec (one line per S, works-row and N), where it changes, the
   caveats that apply, the number of tasks, and any remaining finding. Ask: approve / change X /
   stop / escalate to full. In plan mode, change.md is the plan you hand to `ExitPlanMode`. On
   approval set `status: approved` and add the feature's row to the central index, in the columns
   the index already has, with track `small` and the link pointing at `change.md`.
3. **Build.** As in `feature-design` *After approval*: branch per the profile (first commit
   `Add change design for <title> (#<N>)`), implement test first ticking tasks, and on merge set
   `status: implemented` and add the history rows. If a full-track trigger or a new S/N/O item turns up
   while building, stop: amend change.md and re-gate, or escalate. Do not build past the spec.

## Escalate to full

Stop and escalate when writing, review or building shows any full-track trigger: a migration, a
contract others consume, a new or changed consumer or job, a boundary crossing, a third deployable,
a new external dependency, an auth or tenancy change, a decision that needs an ADR, or a §2.3 that
keeps growing past what one person can hold in their head.

1. Tell the user in one line, with the evidence (`path:line` or the caveat answer). Ask to promote.
2. On agreement, in the same folder:
   - create `design.md` from `../feature-design/templates/design.md` and copy §1 and §2 over
     unchanged;
   - rebuild the frontmatter for the full track: `track: full`, `status: proposed`,
     `review: { stage1: pending, … }`, add `adrs: []` and `specs: []`;
   - under §1 add `Promoted from the small track on <date>: <trigger> — <evidence>`, so the reason
     survives;
   - delete change.md. Its §3–§7 and review get redone by the full track, which needs more than
     they hold.
3. If the new scope added behaviour the issue's acceptance criteria don't cover, draft the extra
   criteria, ask whether to add them to the issue, and number them on from the existing ones.
4. Continue with `feature-design` Stage 1 from *Where it fits*. If the profile has no
   `system-base.mmd` yet, create it first as that skill's *Project profile* describes.

If the person keeps the small track despite a trigger, record it in §7 as
`Override: <trigger> — <their reason>` and do not raise the same trigger again; the reviewer
reports it once as an accepted risk. Do not downgrade a full design to small unless the user asks.
