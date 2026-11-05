---
name: feature-design
description: Use whenever someone asks for a full design, a system design, a design with sequence, data-flow or ER diagrams, or to escalate a small change to the full design, and whenever start-change routes work to the full track (migrations, contract changes, new consumers, jobs or services, boundary crossings, more than two deployables, new dependencies, auth changes, new multi-step flows). The full track of the feature workflow — no code without a written spec of what the change does, how we'll know it works, what it must not break and what on-call would need to debug it at 3 am — from an issue to an approved system design (the spec, where it fits, sequence, control, data-flow and data-model diagrams, affected parts, caveats, concurrency and idempotency, decisions) and then a separate approved implementation plan (ordered test-first tasks), each scrutinised by the design-reviewer agent and approved by a person before the next step.
---

# Feature design: issue → system design → implementation plan

Two documents and two approvals, in this order. The **system design** answers: where does this
sit in the system, what does it touch, what could go wrong, what do we decide. The
**implementation plan** answers: which code, in which order, with which tests. Never write the
plan before the design is approved, and never write code before the plan is approved.

**No code without a written spec.** Every design opens with a spec (§2) that answers four
questions, and every plan proves all four:

1. **What the change does**: observable behaviour, as numbered statements S1, S2, …
2. **How we'll know it works**: for each statement and acceptance criterion, the evidence (a
   named test, a manual check with its expected result, or a production signal with its value).
3. **What it must not break**: the neighbouring behaviour, contracts, data and guarantees,
   numbered N1, N2, …, each with the existing or new test or check that guards it.
4. **How we'll debug it at 3 am**: *if I were on call at 3 am and this broke, what observability
   would I need to solve it?* For each realistic failure mode, numbered O1, O2, …: how we find out
   (alert or symptom), the signal that localises it (log line with its fields, metric, trace span)
   and what it tells on-call to do first. Observability is designed here, before the code, not
   added after the first incident.

If you cannot answer one of them, the design is not ready to review. Ask the user rather than
writing a vague answer.

## Project profile

Read `.claude/profiles/feature-workflow.md`. If it is missing, create it with the user from
`templates/profile.md` (five minutes, once per repo). It names:

- the features directory (default `features/`) and index file;
- the issue tracker commands (default GitHub: `gh issue view/create`), labels, board;
- the **tracks**: branch naming (default `feature/<N>-<slug>` for small and full, `trivial/<slug>`),
  the trivial threshold, and project-specific full-track triggers (read by `start-change`);
- where the list of deployable parts comes from (a deps manifest, the solution, workspaces);
- the specs directory, the ADR directory, template and index;
- the system base diagram (`system-base.mmd`). Create it on first use: one node per
  deployable, store and broker, grouped by bounded context in subgraphs, drawn by `references/diagrams.md` (shapes,
  edges and the class block), everything `:::quiet`;
- which **caveat packs** in `references/caveats.md` apply (core always; messaging, gateway,
  web-frontend, data, AI as the stack has them) and any project-specific caveat rows;
- enforcement, if any (hooks or CI that check `status:` and `review:` frontmatter).

## Stage 0 — the issue

1. **Given an issue**: read it with its comments. The body is the problem statement, so quote and
   condense it rather than restating it from the chat.
2. **No issue yet**: draft one: **Problem**, **Who is affected**, **Acceptance criteria**
   (checklist), **Out of scope**, from what the user said and what you can verify in the
   code. Show the draft and ask once whether to create it. Add it to the board if the profile
   names one; if that fails (no scope, no board), say so in one line and continue.
3. Slug: kebab-case, 2–4 words, from the title. Feature id `<N>-<slug>`.
4. Look for prior art (older design docs, ADRs, closed issues on the same ground) and say what
   the design keeps from it.

## Stage 1 — system design

Write `<features>/<N>-<slug>/design.md` from `templates/design.md`. Rules per section:

- **Frontmatter**: fill every key. `produced_by.model` is the model id you run as, `tool` the
  client and mode, `effort` only if known. `author` is the git user. Keep `review` on one line
  in flow style (`{ stage1: pending, by: design-reviewer, date: … }`) so hooks can grep it.
  `status` stays `proposed` until a person approves. `status: approved` is the person's
  approval and `review` is the reviewer's verdict; the gates need both.
- **Problem**: condensed from the issue; acceptance criteria copied verbatim.
- **Spec** (§2), written before any diagram:
  - *What it does*: behaviour from the outside ("When <actor> <does>, <observable result>"),
    not the build. Each acceptance criterion is covered by at least one S-statement.
  - *How we'll know it works*: one row per S-statement and per acceptance criterion, naming the
    evidence. Prefer an automated test named `Class.Method`. A production signal names the
    query and the value that means "working".
  - *What it must not break*: find the neighbours by reading the code. Look at the existing callers of
    what you change, the contracts and their consumers, the stored data a migration touches, the
    screens and flows next to the change, and the guarantees in the specs and ADRs. Each gets a guard:
    an existing test (cite it, and confirm it exercises the behaviour) or a new regression test
    or check. The caveats pass usually adds rows here, so revisit §2.3 after §9.
  - *How we'll debug it at 3 am*: list the failure modes from the control flow and the caveats (a
    dependency times out, a message is dead-lettered, a duplicate is dropped, a migration stalls, a
    user is denied). For each, picture on-call with only the dashboards, logs and traces, no code and
    no debugger: what tells them it is happening, what tells them where and for which record, and
    what they do first. Every signal named here is something a task in the plan produces (and a test
    asserts where it can: the log line is written, the metric increments); a new alert or dashboard
    is a task too, as code if the project keeps them as code. Prefer the project's existing
    telemetry conventions (correlation id, span names, metric naming) over new ones. "We'll add
    logging" is not an answer.
- **Where it fits**: copy the project's `system-base.mmd`; mark changed nodes `:::affected`,
  new ones `:::new`, leave the rest `:::quiet`, add new links as `==>`. Change nothing else, so two
  designs stay comparable.
- **Diagram rules**: every diagram follows `references/diagrams.md`: one question per sheet,
  about twelve nodes at most, colour only for changed, new and failure, one shape and edge per kind
  of thing, labels on one line naming the real route, message or table, and the shared class block.
  The system map is `flowchart LR`; a pipeline of more than eight steps is `flowchart TB`.
- **Main flow**: one `sequenceDiagram` per user-visible flow, naming the route, request and
  response types, the messages, the handlers, the timeouts and the status codes.
- **Control flow**: a `flowchart TD` of authorisation, validation, branches, errors, retries,
  timeouts and duplicate delivery. Every branch ends in an observable outcome (status code,
  event, UI state). The error mapping and the idempotency story become explicit here, before
  any code exists.
- **Data flow**: `flowchart LR`, cylinders for stores, every edge labelled with the data or
  contract it carries. Anything that crosses a context boundary shows how it crosses (message,
  gateway-carried, duplicated) and agrees with the caveats.
- **Data model and states**: an `erDiagram` for new or changed tables/columns/indexes (mark
  the owner), a `stateDiagram-v2` for any new or changed lifecycle, or "n/a — reason". The
  migration named in Affected parts must match the diagram.
- **Affected parts**: one row per deployable/project, named as the profile's source names
  them. If the stack has a fan-out tool (shared contracts compiled by many services), run it
  and list the fan-out.
- **Caveats**: go through `references/caveats.md` (core + the profile's packs) row by row.
  For each, write an answer or `n/a — reason`. **Open the file the row points at**; do not answer
  from memory.
- **Concurrency and idempotency** (9.1): required whenever the feature writes state or adds
  or changes a consumer, job, saga or loop. Fill both tables. Each row names the mechanism,
  the code it relies on and the observable outcome. Check that the mechanism is *wired*, not
  only registered. Draw a `sequenceDiagram` per race the design resolves (who waits, who wins,
  what the loser sees). Say what is left to another feature.
- **Decisions**: numbered, each with a decision, a rationale and the rejected alternative. A decision
  that sets a rule other features must follow gets an ADR.
- **Specs**: which living capability specs this feature edits, or the new one it adds.

Then:

1. **Review.** Run the `design-reviewer` agent with
   `STAGE=1. Review <features>/<N>-<slug>/design.md for issue #<N>.` Its report has a **spec check**, a **risk
   map**, the **problematic patterns** it sees (`references/patterns.md`), and **findings**.
   Copy the spec check, the map and the patterns into **Review outcome** verbatim, because they are what the
   approver reads first. Fix each finding you agree with. For one you keep, write
   `Accepted: <finding> — <reason>`. A pattern chosen deliberately stays listed with its
   reason. Re-run the reviewer until it reports no blockers, then set `review.stage1` to
   `passed` or `accepted-risks` with the date.
2. **Render.** Copy `references/render.html`. Replace `<!--TITLE-->` (both places) with the
   feature title, `<!--ISSUE-->` with `#<N>`, `<!--DATE-->` and `<!--MODEL-->` with the model name,
   and `<!--SHEETS-->` with one sheet per Mermaid block, the source copied unchanged:
   ```html
   <section class="sheet" data-sheet="3" data-title="Where it fits"
            data-caption="Orders.Api and the orders db change; Billing gains a refund consumer.">
   <script type="text/x-mermaid">
   flowchart LR
   …
   </script>
   </section>
   ```
   `data-sheet` is the design section number; `data-caption` is one sentence saying what changed
   on this sheet, which is what the approver reads first. Two sheets from one section number get
   `3a`, `3b`. The page builds the title blocks, contents and key, and re-colours the class block for
   dark mode; a sheet that fails to parse shows the error and its source, so fix it before publishing. Publish it where the user can see rendered diagrams (an
   Artifact in Claude Code; otherwise link the Markdown on the branch, since GitHub renders Mermaid).
3. **Gate.** Present the design in one short message, in this order: the **spec** (does / we'll
   know it works when / must not break / debug at 3 am, one line per item), the risk map, the
   patterns and how each was handled, the diagrams link, affected parts, the concurrency and
   idempotency summary (including what is deferred), the caveats that are not n/a, the decisions,
   and the remaining findings. Ask for approval (approve / change X / stop). Do not start Stage 2
   until it is approved, then set `status: approved`.

## Stage 2 — implementation plan

Write `plan.md` from `templates/plan.md`, only after Stage 1 is approved.

- §0 restates the spec in one line per item, so the plan reads on its own.
- Tasks grouped by project in dependency order (contracts → handlers → gateway → generated
  clients → UI → specs/ADRs/indexes). Each task gives **Test first** (test class and method,
  and why it fails today), the files, the spec items it serves (S/N/O numbers), and the skill to
  use if one exists. A task that serves no spec item is scope creep, so cut it or add the item
  to the design (and re-review).
- A bookkeeping section always exists: spec edits, ADRs (or "none"), version bumps the stack
  requires, the index row, per-project history rows.
- **Verification proves the spec**: every row of design §2.2 ("it works"), §2.3 ("nothing
  it must not break is broken") and §2.4 ("we could debug it at 3 am") appears in plan §5 with the task that produces its evidence,
  plus exact commands and the journeys to walk. The PR is ready when every row is ticked.

Then:

1. **Review**: `design-reviewer` with `STAGE=2. Review … design.md and plan.md for issue #<N>.`
   Same loop; set `review.stage2`.
2. **Index**: add the feature's row to the central index. Its status equals the design's.
3. **Gate**: in plan mode, the plan you hand to `ExitPlanMode` is this `plan.md`. Otherwise ask
   for approval directly. On approval set `status: approved` in `plan.md`.

## After approval

- Branch per the profile. First commit: the feature folder, index row and any ADR
  (`Add design and plan for <title> (#<N>)`).
- Implement by the plan, test first, ticking tasks; edit specs in place.
- On merge: `status: implemented` in both documents, move the index row, and add the per-project
  history rows. `implemented` is terminal. A follow-up is a new feature or a trivial fix.

## Tracks

This skill is the **full** track. The `start-change` skill routes work here, to `change-design`
(small: one short document, one gate) or to a trivial branch with no document. A small change that
is escalated arrives with a `design.md` whose §1 and §2 are already filled from its change.md:
check them against the issue, then continue from *Where it fits*.
