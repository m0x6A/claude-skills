# grafana-ops

Run production investigations from live Grafana data, and keep alerts and dashboards as code.

- **grafana-stack-profile**: discovers your stack once (datasource UIDs, the label that scopes your
  app on a shared stack, services, Loki index labels vs structured metadata, heartbeat, entry-point
  dashboards, alert routing, noise filtered by design) and writes `.claude/profiles/grafana.md`.
- **grafana-investigate**: trust check first (is telemetry even flowing?), then RED blast
  radius, domain counters, logs, one trace end to end, deploy correlation, and the code behind it.
  Reports with evidence and never changes anything.
- **grafana-as-code**: the repo is the source of truth. Ships `scripts/` (offline linter for scoping,
  the instant → reduce → threshold rule shape, uids and grid; publishers with `--prune`; a live
  verifier) and `templates/` (config, CI workflow, example rule and dashboard).
- **reliability-reviewer** agent: dead letters, outbox backlog, self-healing loops, readiness, and
  breakers, traced back to `path:line`.

## Setup

Run the [Grafana MCP server](https://github.com/grafana/mcp-grafana) with `GRAFANA_URL` and a
**Viewer** service-account token (`GRAFANA_SERVICE_ACCOUNT_TOKEN`). Then ask Claude to "set up the
Grafana stack profile". Publishing from CI needs an Editor token as `GRAFANA_API_TOKEN`; the scripts
need Python 3.10+ and PyYAML.
