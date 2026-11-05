---
name: grafana-investigate
description: Investigate a production error, outage, latency spike or anomaly from live Grafana data (Prometheus/Mimir metrics, Loki logs, Tempo traces) through the grafana MCP server, starting with a check that the telemetry can be trusted at all. Use when asked why something is failing in prod, what happened at a given time, whether a deploy broke something, to root-cause an alert, or when someone says "it's slow", "users see errors" or "nothing shows in Grafana" — even without naming Grafana.
---

# Investigate a production issue with Grafana

Read `.claude/profiles/grafana.md` first. It holds the datasource UIDs, the scope
matcher, the service names and the Loki label model. If it is missing, run the
`grafana-stack-profile` skill before step 1; ten minutes there saves an hour of
empty queries. Below, `<scope>` means the profile's scope matcher (for example
`service_namespace="acme"`) and goes into **every** selector.

The MCP server is for reading. Never try to fix anything through it, even when the
token would allow it: fixes go through code, or through dashboards and alerts as code.

## Procedure

1. **Trust check first, always.** Before you interpret any *absence* of errors,
   prove the affected service is still exporting:
   `sum by (service_name) (rate(<heartbeat>{<scope>}[5m]))`.
   A missing series means the pipeline is broken, so "no errors in Grafana" means
   nothing and the broken pipeline is the finding. Check the platform's own
   view (container/revision state, pod events) instead. With no heartbeat metric,
   use the request-rate series of a service that always has traffic, and say the
   check is weaker.
2. **Scope the blast radius** with RED metrics, by `service_name`, over a window
   that brackets the incident with at least as much quiet time before as after:
   request rate, 5xx ratio (guard the divisor), p95 from the duration histogram.
   Name *which* services changed, *when* (to the minute), and *which way*. Capture
   the matching dashboard panel with `get_panel_image` as evidence.
3. **Check the domain counters** for the affected area (the profile lists them):
   failure counters by reason, retries, dead letters, outbox/queue depth, circuit
   breaker state, exceptions by type. With low traffic, use absolute counts over 15
   minutes (`increase(...[15m])`) rather than ratios, which swing wildly on three
   requests.
4. **Read the logs** for the service and window, Warning and above:
   `{<scope>, service_name="<svc>"} | <level_field>=~"Warning|Error|Critical"`.
   Structured-metadata fields are filtered directly, with no `| json`. Use
   `query_loki_patterns` to collapse a flood into its few distinct shapes before you
   read individual lines. Pivot to traces with the line's `trace_id`.
5. **Follow one trace end to end.** With the proxied `tempo_*` tools:
   `{ resource.service.name = "<svc>" && status = error }`, or `{ trace:id = "<id>" }`
   from a log line, or a session/tenant attribute from the profile. Without them,
   use `grafana_api_request` against the Tempo datasource proxy. Find the span where the
   time or the error lands: gateway timeout, consumer, database, external call.
   `generate_deeplink` gives the user an Explore link.
6. **Correlate with change.** Line the inflection point up against deploys
   (`gh run list --workflow=<release workflow>`, release tags, `service_version`
   changing in the metrics), config changes, and traffic shifts. Something changing
   at the same minute is a lead, not proof. Look for the mechanism.
7. **Read the code behind the anomaly.** Open the consumer, endpoint or worker the
   trace points at and confirm the mechanism (missing timeout, swallowed exception,
   static state across replicas, unbounded query, retry storm). Cite `path:line`.
8. **Check known failure modes** in the project's runbooks before you call
   something novel.

## Traps

- **Grouping is not filtering.** `sum by (service_name)(...)` without `<scope>` on a
  shared stack mixes in other apps.
- **Range limits.** Query windows longer than the datasource allows fail or
  silently downsample. Split long windows, and say which window you looked at.
- **Never-fired counters look missing.** A counter that has not been emitted since start
  does not exist; that is not the same as zero. Check whether the app zero-seeds.
- **Filtered by design.** Health probes, `SELECT 1`, telemetry relay calls and
  outbox polling are often dropped at export (the profile lists them). Their absence
  is not a gap, and the errors that survive the filter are real.
- **`service_version` may not be the image tag.** Check the profile before you
  attribute a regression to a release.
- **Alert silence.** A rule in `health: error` never fires. `alerting_manage_rules
  list` before you trust that "nothing alerted".

## Report

1. **Timeline**: UTC timestamps, what changed, which services.
2. **Evidence**: each query you ran, the number it returned, panel images or deeplinks.
3. **Root cause** with the code path (`path:line`), or **ranked hypotheses**, each
   with the query or test that would settle it.
4. **Smallest safe change** and what would have caught it earlier (missing alert,
   missing panel, missing heartbeat). Hand the alert to `grafana-as-code`.

Never restart, redeploy, purge or redeliver anything. Recommend and stop.

## Setup

The grafana MCP server needs `GRAFANA_URL` and a Viewer-role
`GRAFANA_SERVICE_ACCOUNT_TOKEN` in the environment before the session starts. If the
server is not connected, that setup is the blocker. Say so rather than guessing
from code alone.
