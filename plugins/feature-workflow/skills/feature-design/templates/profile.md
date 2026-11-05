# Feature workflow profile — <project>

Read by the `start-change`, `change-design` and `feature-design` skills and the `design-reviewer` agent. Commit it as
`.claude/profiles/feature-workflow.md`.

## Layout
- Features directory: `features/` · central index: `features/README.md`
- Per-project history file: `FEATURES.md` next to each project's `AGENTS.md` (or "none")
- Living specs: `spec/<capability>.md` (or "none")
- ADRs: `doc/architecture/ADR-NNN-*.md` · template: `…` · index with next free number: `…`
- System base diagram: `.claude/profiles/system-base.mmd`

## Tracker
- Issues: GitHub (`gh issue view <N> --json number,title,body,labels,comments`)
- Labels for a feature: `type:feature` + area labels: `backend`, `frontend`, `database`, …
- Board: `gh project item-add <number> --owner <owner> --url <issue>` (or "none")

## Tracks (read by start-change)
- Branches: small and full `feature/<N>-<slug>` · trivial `trivial/<slug>`
- Trivial threshold: ≤ 100 changed lines under `src/`, ≤ 2 projects, issue referenced, no behaviour change beyond the fix
- Small: everything that is neither trivial nor full (default)
- Full-track triggers: the defaults in `start-change` (migration, consumed contract, consumer/job/saga,
  boundary crossing, > 2 deployables, new dependency, auth/tenancy, new multi-step flow), plus:
  - `<project-specific trigger, e.g. anything under src/Payments/>`
  - remove: `<a default that does not apply here, with the reason>`

## Deployables
- Source of truth for names: `<deps manifest | solution | workspace list>`
  (e.g. `jq -r '.services[].name' .github/service-deps.json`)
- Fan-out tool for shared contracts: `<command>` (or "none")
- Version bump rule: `<e.g. every changed service bumps version.json>` (or "none")

## Caveat packs (references/caveats.md)
- core (always) · messaging · gateway · web-frontend · data · ai   ← delete what does not apply
- Project rows:
  | Caveat | Question | Look at |
  |---|---|---|
  | | | |

## Rules the reviewer applies
- Architecture rules: `AGENTS.md` § …, ADR-…
- Do not flag: `<accepted trade-offs every feature shares, e.g. rolling-deploy order of a new message>`

## Enforcement
- `<hooks or CI that check status/review frontmatter, or "none">`
