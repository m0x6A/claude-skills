# feature-workflow

No code without a written spec. The `feature-design` skill takes a feature from an issue to two
documents in `features/<N>-<slug>/`, each reviewed by the `design-reviewer` agent and approved by a
person before the next step:

1. **design.md** opens with the spec: *what the change does* (S1, S2, …), *how we'll know it works*
   (the evidence for each statement), and *what it must not break* (N1, N2, …, each with its guard). Then
   the system map with affected parts highlighted, sequence, control-flow, data-flow, ER and state
   diagrams, affected parts, a caveats checklist (a core list plus messaging, gateway, web, data and AI
   packs), concurrency and idempotency tables, and numbered decisions.
2. **plan.md** lists ordered, test-first tasks, each tied to spec items, and a verification section that
   proves every "works" and "must not break" row.

The reviewer leads with a spec check, a ranked risk map and the problematic patterns it sees
(`references/patterns.md`), then at most seven findings, checked against the real code.

## Setup

On first use the skill creates `.claude/profiles/feature-workflow.md` with you (layout, tracker,
branch naming, deployables, caveat packs, rules) and a `system-base.mmd` diagram of your system.
It uses `gh` for GitHub issues by default.
