---
name: grafana-stack-profile
description: Discover and record the facts about a project's Grafana stack that every investigation, alert and dashboard depends on — stack URL, datasource names and UIDs, the label that scopes this app on a shared stack, service names, which Loki fields are index labels versus structured metadata, the heartbeat metric, entry-point dashboards, alert labels and contact point, and what noise is filtered at the source. Writes `.claude/profiles/grafana.md`. Use the first time grafana-ops is used in a repository, when the profile is missing or stale, or when a query returns nothing and the cause may be a wrong label or datasource.
---

# Grafana stack profile

The other grafana-ops skills are generic; this file is what makes them specific to a
project. An investigation that guesses the datasource UID or the service label wastes
its first ten queries and, worse, reads an empty result as "no errors".

Output: `.claude/profiles/grafana.md`, committed to the repository, in the shape of
the template below. Every fact carries the date it was verified.

## Procedure

Use the grafana MCP server. It should be read-only (a Viewer service-account
token); if it is not, say so and do not write through it.

1. **Stack and datasources.** `list_datasources`; record name → uid → type for the
   Prometheus/Mimir, Loki and Tempo datasources the app uses. On Grafana Cloud the
   uid (`grafanacloud-prom`) differs from the name (`grafanacloud-<stack>-prom`);
   tools want the uid, provisioning files often want the name. Record both.
2. **Is the stack shared?** `list_prometheus_label_values` for `service_namespace`,
   `job` and `service_name`. If more than one application reports, find the label
   that isolates this one (usually `service_namespace` from the OTel resource, else a
   `service_name` prefix) and record it as the **scope matcher**. Every query any
   skill writes then carries it. Warn: `sum by (service_name)` *groups*; it does not
   *filter*.
3. **Services.** List this app's `service_name` values, including transient jobs
   (migrations, cron) and the browser if it reports. Note how the name is derived
   (resource attribute, version file, env var) and what `service_version` means:
   is it the image tag, the assembly version, or something else?
4. **Loki label model.** `list_loki_label_names` on the scope selector. Record which
   fields are **index labels** (go in `{...}`) and which are **structured metadata**
   (filtered with `| field="..."` and no parser). Sample one line with
   `query_loki_logs` limit 5 to learn the level field and its vocabulary
   (`severity_text` with `Information|Warning|Error|Critical` for .NET,
   `info|warn|error` elsewhere) and whether lines are JSON, logfmt or rendered text.
   Record whether `trace_id` is present on log lines (the log → trace pivot).
5. **Liveness signal.** Look for a heartbeat or always-on series
   (`list_prometheus_metric_names` with regex `.*heartbeat.*|up|target_info`). If
   there is none, record that, because an absence of errors then proves nothing. Suggest
   adding a 30-second heartbeat counter per service as follow-up work.
6. **Metric naming.** OTLP → Prometheus translation appends units and `_total`
   (`http_server_request_duration_seconds_count`). Record the real names of the RED
   metrics and of any domain counters, and whether counters are zero-seeded at
   startup (if not, `increase()` across a restart undercounts and a never-fired
   counter looks missing).
7. **Traces.** If the Tempo tools are proxied (`tempo_*`), note it; otherwise the
   fallback is `grafana_api_request` against
   `/api/datasources/proxy/uid/<tempo-uid>/api/search?q=<TraceQL>&start=&end=`.
   Record useful span attributes (session id, journey, tenant) and retention.
8. **Dashboards and alerts.** `search_dashboards` / `search_folders` for the app's
   folder and uid prefix; pick the two or three entry points (is anything wrong,
   where, can the data be trusted). `alerting_manage_rules list`: record the label
   that marks this app's rules, the contact point, and any rule currently in
   `health: error` (it will never fire).
9. **Noise filtered at the source.** Read the app's telemetry setup (OTel
   processors, samplers, log filters) and list what is dropped by design (health
   probes, `SELECT 1`, outbox polling, the telemetry relay). Absence of those is not
   a gap.
10. **Deploys and retention.** How releases are identified (git tags, a release
    workflow, image tags) so a metric inflection can be lined up with a deploy;
    query-range limits and retention per signal.
11. **Where fixes go.** Dashboards and alerts as code? Which directory, which
    publish workflow (see `grafana-as-code`)? Runbooks?

Write the file, show the user a summary of anything surprising (shared stack, no
heartbeat, rules in error, missing trace ids), and commit it on their go-ahead.

## Template

```markdown
# Grafana stack profile — <app>
Verified: YYYY-MM-DD via grafana MCP (Viewer token)

## Stack
- URL: https://<stack>.grafana.net · shared with: <other apps or "no">
- Scope matcher (add to EVERY query): `service_namespace="<app>"`
  - TraceQL: `resource.service.namespace = "<app>"`

## Datasources
| Signal | Name | UID |
|---|---|---|
| Metrics | | |
| Logs | | |
| Traces | | |

## Services
<list of service_name values> · derived from: <…> · service_version = <image tag | …>

## Logs
- Index labels: <…>  · Structured metadata: <…> (filter with `| field="…"`, no parser)
- Level field and values: `severity_text` = Information|Warning|Error|Critical
- trace_id on lines: yes/no

## Liveness
`sum by (service_name) (rate(<heartbeat>{<scope>}[5m]))` — every live service, every 30 s

## Metrics
- RED: <request counter / histogram names>
- Domain counters (zero-seeded: yes/no): <name — labels — meaning>

## Traces
- Tools: proxied tempo_* | API fallback · Retention: <…>
- Useful attributes: <…>

## Dashboards and alerts
- Folder / uid prefix: <…> · Entry points: <uid — question it answers>
- Alert label: `app=<app>` · Contact point: <…> · Rules in error at last check: <…>

## Filtered by design (absence is not a gap)
- <…>

## Deploys and limits
- Releases: <tags / workflow> · Range limits: metrics <…>, logs <…>, traces <…>

## Changing things
- Dashboards/alerts as code in: <dir> · published by: <workflow> · Runbooks: <path>
```
