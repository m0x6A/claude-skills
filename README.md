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
| **voice-issue** (a mod) | `/voice-issue` and a 🎙 button above the prompt: speak, review the drafted issue, create it with `gh` | — | none; `/voice-issue setup` installs what it needs |
| **issue-picker** (a mod) | `/issues`: list the repository's open issues, filter, pick one and start Claude on it here or in a new tmux window | — | none; needs a logged-in `gh` |
| **dockge** | `dockge-deploy`: publish the image, write a pinned stack with a free port and secrets on the host, deploy after approval, prove it answers, keep the rollback tag | — | `.claude/profiles/dockge.md` |

## Principles the skills share

- **No code without a spec.** `change-design` and `feature-design` make every design answer *what the
  change does*, *how we'll know it works* and *what it must not break*, and the tasks must prove all
  three. `start-change` decides how much ceremony the change needs, not whether it gets a spec.
- **Design for 3 am.** Every design, build and review skill asks: *if I were on call at 3 am and this
  broke, what observability would I need to solve it?* The answer (the alert, the log line with its ids,
  the trace) is designed and tested with the change, not added after the first incident.
- **Concentrate human attention.** Reviews lead with a ranked map of at most three places to look,
  each with a check a person can do in a minute, instead of a flat list of findings.
- **Trust the data before reading it.** Investigations prove that telemetry is flowing before
  they treat an absence of errors as good news.
- **Evidence, not memory.** Every finding cites `path:line` or the query and the number it returned.
- **Read-only by default.** Agents report; they never restart, redeploy, purge or edit production.

## Model and effort

Each agent gets the cheapest model that still does its job well. How bad a miss would be counts for
more than the token bill. Models are named by alias, so agents move to new releases without edits.

| Agent | Model | Effort | Why |
|---|---|---|---|
| `design-reviewer` | opus | high | Runs rarely, at each human gate. A missed contradiction or concurrency bug here becomes production code. |
| `reliability-reviewer` | opus | high | Used during incidents. A wrong "it recovers on its own" verdict costs more than any token bill. |
| `architecture-guardian` | sonnet | high | Runs before every backend merge and checks a diff against rules that are already written down. |
| `ux-critic` | sonnet | medium | Screenshots and page text make up most of its tokens. Its judgment comes from the written craft standards. |
| `docs-reconciler` | sonnet | low | Mechanical work: comparing documents with the code and fixing the wording. |

Skills run in your conversation and keep **your** model, because a model set in a skill would
silently override the one you picked. Four of them ask for `effort: high` where shallow reasoning
produces confidently wrong output: `feature-design`, `grafana-investigate`, `review-hotspots` and
`architecture-review`.

To override the defaults, set `CLAUDE_CODE_SUBAGENT_MODEL` to run every subagent on one model, or copy an
agent into `.claude/agents/` and change its `model:`. For an unusually risky design (money, auth, data
loss), consider running `design-reviewer` on `fable`.

## Validation

Every pull request runs `.github/workflows/validate.yml`; run the same checks locally before you push:

```bash
tools/validate.sh          # everything (the Mermaid render needs Node and Chrome)
tools/validate.sh --fast   # skip the Mermaid render
```

- **`claude plugin validate --strict`** on the marketplace and every plugin.
- **`tools/validate_skills.py`**: skill and agent frontmatter (name matches folder, description within
  1024 characters, body under 500 lines, every agent names a known model, every effort is a known
  level); every `references/`, `templates/` and `scripts/` path a skill
  mentions exists; every skill or agent named in prose exists; marketplace entries match each
  `plugin.json`; a plugin changed since `main` has bumped its version; both READMEs mention every skill
  and agent; the feature-workflow diagram palette is the same in the style guide, template and render
  page; JSON, YAML and Python parse.
- **`tools/check_mermaid.py`**: every Mermaid diagram in the repository renders.
- **Script tests**: each skill's `scripts/tests` suite.

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
