---
name: grafana-as-code
description: Keep Grafana alert rules and dashboards as code in the repository — lint them offline (scoping on a shared stack, the instant→reduce→threshold rule shape, unique uids, grid overlaps), publish them from CI with prune, and verify against the live stack that every rule evaluates and every panel query matches data. Use when adding an alert for a new failure mode, tuning a threshold, adding or changing a dashboard or panel, setting up alerts/dashboards-as-code in a new repo, or when a rule sits in "Error" or a panel says "No data".
---

# Grafana alerts and dashboards as code

The repository is the single source of truth. The Grafana UI is read-only for these
resources: rules are published with provenance `api`, so the UI shows them locked,
and a publish with `--prune` deletes whatever the repo no longer has. Anything edited
live gets overwritten.

Read first: `grafana-as-code.json` (the project's config, see `templates/`), and
`.claude/profiles/grafana.md` if it exists (datasources, scope matcher, metric names).
For query and JSON-schema expertise, the upstream Grafana skills (`promql`, `loki`,
`dashboarding`, `alerting-irm` from `grafana/skills`) complement this one.

Details: `references/alerts.md` (rule shape, conventions, failure modes) and
`references/dashboards.md` (layout, variables, units, naming). Load the one you need.

## The tooling (in this skill's `scripts/` directory)

| Command | What it does |
|---|---|
| `python3 scripts/lint.py [--config PATH]` | Offline, no credentials. Prints one `ERROR:` line per problem and exits 1 if there are any. This is the CI gate. |
| `python3 scripts/publish_dashboards.py [--config PATH] [--dry-run] [--prune [--allow-mass-prune]] [NAME ...]` | Pushes dashboards; datasource names are resolved to `{type, uid}`. |
| `python3 scripts/publish_alerts.py [--config PATH] [--dry-run] [--prune [--allow-mass-prune]] [--skip-contact-point] [--adopt-contact-point] [NAME ...]` | Pushes rules (provenance `api`), resolves placeholders, provisions the contact point from the env var the config names. |
| `python3 scripts/verify_live.py [--config PATH] [--alerts-only \| --panels-only] [--strict] [--lookback 30d]` | `--alerts-only` fails if any of this app's rules is in error or missing; the panel check is advisory unless `--strict`. |
| `python3 -m unittest discover -s scripts/tests` | The tooling's own tests. |

Behaviours worth knowing: unknown config keys are an error, so a typo cannot silently switch off a
check (keys starting with `_` are comments). A missing optional key disables its check with a
one-line `notice:`. `--prune` is refused unless both `folder` and the uid prefix are set, and it is
ignored when names are passed.

Safety guards (the publish fails rather than destroys):
- **Prune never runs when nothing was published.** An empty directory, or files with no
  rules, would otherwise delete everything. No flag overrides this.
- **Prune stops before deleting more than half of the app's live items** (and more than two).
  A deliberate clean-up passes `--allow-mass-prune`, run by a person, not added to CI.
- **The contact point is only overwritten if this tool provisioned it** (provenance `api`).
  One of the same name made in the UI may belong to another team: rename yours, or pass
  `--adopt-contact-point` once if it really is yours.

All four read `grafana-as-code.json` (`--config PATH`, or `GRAFANA_AS_CODE_CONFIG`,
or the nearest one walking up from the working directory). Credentials come only
from the environment: `GRAFANA_URL`, `GRAFANA_API_TOKEN` (Editor for publish, Viewer for verify).

## Setting it up in a repository (once)

1. Copy `scripts/` into the repo (for example `telemetry/grafana/`) so CI runs a
   pinned copy, not the plugin's.
2. Copy `templates/grafana-as-code.json` to the repo root and fill it from the
   stack profile: dirs, folder, uid prefixes, the **scope** matcher, datasource names,
   placeholders, contact point, required rule labels.
3. Export what already exists live (`get_dashboard_by_uid` per dashboard; the
   provisioning export API for rules) into the dirs, then run the linter and fix
   what it finds *before* the first publish. The first prune deletes everything not
   in the repo.
4. Copy `templates/publish-telemetry.yml` to `.github/workflows/`. Add the secrets
   it names. PRs lint and run the unit tests; merge to main publishes with
   `--prune`, waits one evaluation interval, and fails the run if any rule
   evaluates with an error.
5. Add a README in each dir: the dashboard catalog (uid → question it answers),
   the metric catalog (name → labels → meaning), and the alert table (uid →
   severity → what to do).

## Changing an alert

1. Edit or add the rule in the matching domain file under `alerts_dir`, in the
   canonical shape (`references/alerts.md`). Every rule needs a justification: it
   pages someone or someone reads it, otherwise leave it out.
2. Run the query **as an instant query** against live data through the MCP server.
   The series must exist, and the threshold must not already fire or be unreachable.
3. Lint, then unit tests, then a dry-run publish. Show the user the payload diff.
4. Merge, and CI publishes. Then `alerting_manage_rules list`: `health: ok`, state
   Normal. NoData right after a publish usually means a wrong metric name or a
   counter that has never fired (not zero-seeded).
5. Commit the YAML and the README row together.

## Changing a dashboard

1. Start from the closest sibling JSON. Keep uid ↔ filename aligned.
2. Lint (offline: scoping, variables, grid, uids).
3. `verify_live --panels-only` reports queries that match nothing on the stack. A
   counter that legitimately never fired also shows up, so say which it is.
4. Merge, and CI publishes. Then `get_dashboard_summary` for the uid and
   `get_panel_image` on the key panels with real data. "No data" is usually a
   wrong name (OTLP translation appends units and `_total`) or a matcher that
   matches nothing; check with `list_prometheus_metric_names`.
5. Commit the JSON and the catalog row together.

## Never

- Edit rules or dashboards in the UI, or through a write-capable MCP token.
- Touch the shared notification-policy tree. Rules route with
  `notification_settings.receiver` to this app's contact point, which keeps the app's
  routing out of a tree other teams own.
- Use `noDataState: Alerting` to detect a dead service. Use an expected-service
  list instead (`references/alerts.md`), so idle periods don't page.
