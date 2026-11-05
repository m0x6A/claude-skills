# Feature workflow profile — <project>

Read by the `feature-design` skill and the `design-reviewer` agent. Commit it as
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

## Branches and size
- Feature: `feature/<N>-<slug>` · Trivial: `trivial/<slug>`
- Trivial threshold: ≤ 100 changed lines under `src/`, ≤ 2 projects, issue referenced

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
