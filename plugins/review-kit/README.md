# review-kit

Reviews that spend a person's attention where it matters.

- **review-hotspots**: a "Human review: look here first" map of at most three entries (where, why it
  is dangerous *in this diff*, what to verify by hand in a minute, and a verdict), ranked by hotspot
  (authorisation → schema → message contracts → public API → user-supplied content → CI → telemetry),
  then at most five blocker or should-fix findings. No polish. If the PR has a feature spec, it checks
  each "must not break" guard and "debug at 3 am" signal, and asks the 3 am question of every
  hotspot.
- **architecture-review**: a repeatable, evidence-first audit (boundaries, gateway, messaging,
  continuity, operability — could on-call debug the busiest flows at 3 am from signals alone? — error
  handling, configuration) that writes a dated report with severities and a map from
  each finding to the work that owns it.
- **architecture-guardian** agent: a boundary and consistency check of a diff, including the 3 am question for
  every new failure path, ending with a verdict.
- **docs-reconciler** agent: fixes guidance docs (ADR index, agent guide, debt registers, feature
  indexes, mirrored skills) to match the code.

## Setup

Works out of the box with your `AGENTS.md`/`CLAUDE.md`. Optionally add `.claude/profiles/review.md`
(hotspot overrides, noise paths, things not to flag) and `.claude/profiles/architecture.md` (boundary
rules, grep set, test commands, report location).
