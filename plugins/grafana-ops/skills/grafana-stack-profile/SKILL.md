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

Use the [gcx CLI](https://github.com/grafana/gcx) with a read-only (Viewer
service-account) token. If the token can write, say so, and still never run a gcx
command that changes Grafana (`create`, `update`, `delete`, `push`, `upsert`,
`restore`, `gcx api` with `-X` or `-d`). `<prom>`, `<loki>` and `<tempo>` below are the
datasource UIDs found in step 1, passed as `-d`. Add `-o json` where you need exact
values.

1. **Stack and datasources.** `gcx config check` first; record the context name and
   the server URL. Then `gcx datasources list -o json` (or `--type prometheus`, `loki`,
   `tempo`): record name → uid → type for the Prometheus/Mimir, Loki and Tempo
   datasources the app uses. On Grafana Cloud the uid (`grafanacloud-prom`) differs
   from the name (`grafanacloud-<stack>-prom`); gcx wants the uid, provisioning files
   often want the name. Record both. Offer (do not run unasked, since it changes the
   person's gcx config) to set them as the context's defaults so later queries need
   no `-d`: `gcx config set contexts.<context>.datasources.prometheus <prom>`, and
   the same for `loki` and `tempo`.
2. **Is the stack shared?** `gcx metrics labels -d <prom> --label service_namespace`,
   then `--label job` and `--label service_name`. If more than one application
   reports, find the label that isolates this one (usually `service_namespace` from
   the OTel resource, else a `service_name` prefix) and record it as the **scope
   matcher**. Every query any skill writes then carries it. Warn: `sum by
   (service_name)` *groups*; it does not *filter*.
3. **Services.** `gcx metrics labels -d <prom> --label service_name --match '{<scope>}'`
   lists this app's `service_name` values; include transient jobs (migrations, cron)
   and the browser if it reports. Note how the name is derived (resource attribute,
   version file, env var) and what `service_version` means: is it the image tag, the
   assembly version, or something else?
4. **Loki label model.** `gcx logs labels -d <loki> --query '{<scope>}'` lists the
   **index labels** (they go in `{...}`). Sample lines with
   `gcx logs query -d <loki> '{<scope>}' --since 1h --limit 5 -o json`: fields on the
   lines that are not index labels are **structured metadata** (filtered with
   `| field="..."` and no parser). The sample also shows the level field and its
   vocabulary (`severity_text` with `Information|Warning|Error|Critical` for .NET,
   `info|warn|error` elsewhere) and whether lines are JSON, logfmt or rendered text.
   Record whether `trace_id` is present on log lines (the log → trace pivot).
5. **Liveness signal.** Look for a heartbeat or always-on series:
   `gcx metrics list-names -d <prom> --contains heartbeat --match '{<scope>}'`, then
   `up` and `target_info` with `gcx metrics series -d <prom> '{__name__="up", <scope>}' --since 1h`.
   If there is none, record that, because an absence of errors then proves nothing.
   Suggest adding a 30-second heartbeat counter per service as follow-up work.
6. **Metric naming.** `gcx metrics list-names -d <prom> --match '{<scope>}' --limit 0`
   gives the real names. OTLP → Prometheus translation appends units and `_total`
   (`http_server_request_duration_seconds_count`). Record the real names of the RED
   metrics and of any domain counters, and whether counters are zero-seeded at
   startup (if not, `increase()` across a restart undercounts and a never-fired
   counter looks missing).
7. **Traces.** `gcx traces labels -d <tempo> --scope resource` and
   `gcx traces labels -d <tempo> --scope span` list the attributes;
   `gcx traces labels -d <tempo> -l resource.service.name` checks the app's services
   are there. Fetch one trace (`gcx traces query`, then `gcx traces get --since 1h --llm -o json`)
   to confirm traces resolve. Record useful span attributes (session id, journey,
   tenant) and retention.
8. **Dashboards and alerts.** `gcx dashboards search --folder <folder name>`, or
   `gcx dashboards search "<app>"`, for the app's folder and uid prefix; pick the two
   or three entry points (is anything wrong, where, can the data be trusted).
   `gcx alert rules list --limit 0 -o wide` (and `-o json` for labels): record the
   label that marks this app's rules, the contact point, and any rule whose health is
   `error` (it will never fire).
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
Verified: YYYY-MM-DD via gcx (Viewer token)

## Stack
- URL: https://<stack>.grafana.net · gcx context: <name> · shared with: <other apps or "no">
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
- Retention: <…>
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
