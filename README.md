# m0x6a — Claude Code skills marketplace

Skills and agents that started in a production .NET + React microservices codebase, generalised so they
work in any repository. Each plugin keeps the project-specific facts in a small **profile** file
committed to your repo (`.claude/profiles/<name>.md`), which the skills read and help you create on
first use.

```text
/plugin marketplace add m0x6A/claude-skills
/plugin install grafana-ops@m0x6a
```

## Plugins

| Plugin | Skills | Agents | Profile |
|---|---|---|---|
| **grafana-ops** | `grafana-stack-profile` · `grafana-investigate` · `grafana-as-code` (with linter, publisher, live verifier and a CI workflow) | `reliability-reviewer` | `.claude/profiles/grafana.md`, `grafana-as-code.json` |
| **feature-workflow** | `start-change` (routes to trivial / small / full) · `change-design` (small: one spec-and-tasks document, one gate) · `feature-design` (full: issue → spec + system design → implementation plan, each reviewed and approved by a person) | `design-reviewer` | `.claude/profiles/feature-workflow.md` |
| **review-kit** | `review-hotspots` (a "look here first" map, then at most five findings) · `architecture-review` | `architecture-guardian` · `docs-reconciler` | `.claude/profiles/review.md`, `.claude/profiles/architecture.md` (optional) |
| **web-ux** | `design-system-ui` · `ux-review` · `a11y-audit` (WCAG 2.2 AA) · `user-journey-check` | `ux-critic` | `.claude/profiles/ux.md` |
| **dotnet-messaging** | `masstransit-consumer` · `bff-gateway-endpoint` · `ef-core-migration` | — | your `AGENTS.md`/`CLAUDE.md` |

## Principles the skills share

- **No code without a spec.** `change-design` and `feature-design` make every design answer *what the
  change does*, *how we'll know it works* and *what it must not break*, and the tasks must prove all
  three. `start-change` decides how much ceremony the change needs, not whether it gets a spec.
- **Concentrate human attention.** Reviews lead with a ranked map of at most three places to look,
  each with a check a person can do in a minute, instead of a flat list of findings.
- **Trust the data before reading it.** Investigations prove that telemetry is flowing before
  they treat an absence of errors as good news.
- **Evidence, not memory.** Every finding cites `path:line` or the query and the number it returned.
- **Read-only by default.** Agents report; they never restart, redeploy, purge or edit production.

## Complements (install from their own marketplaces)

- Grafana's official skills (`promql`, `loki`, `tempo`, `dashboarding`, `alerting-irm`):
  [grafana/skills](https://github.com/grafana/skills)
- `frontend-design`, `skill-creator` and more: [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official)

## Layout

```text
.claude-plugin/marketplace.json
plugins/<plugin>/
  .claude-plugin/plugin.json
  skills/<skill>/SKILL.md (+ references/, templates/, scripts/)
  agents/<agent>.md
```

## Licence

MIT. See [LICENSE](LICENSE).
