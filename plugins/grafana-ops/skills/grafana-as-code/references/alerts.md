# Alert rules: shape, conventions, failure modes

## The one shape Grafana evaluates

```
A  datasource query   Prometheus: model.instant: true      Loki: queryType: instant (item and model)
B  reduce             type: reduce, reducer: last, expression: A
C  threshold          type: threshold, expression: B, evaluator gt/lt   ← condition: C
```

The API *accepts* a range query wired straight into a threshold. The rule then sits
in `health: error` ("only reduced data can be alerted on") forever, and from the
outside a rule in Error looks like a rule at Normal. The linter rejects that shape,
and the publish workflow waits one interval and fails if any rule still errors.

```yaml
- uid: acme-http-5xx
  title: HTTP 5xx on {{ $labels.service_name }}
  condition: C
  for: 5m
  noDataState: OK
  execErrState: Error
  labels: { severity: warning, app: acme }
  annotations:
    summary: "{{ $labels.service_name }} returned {{ $values.B }} 5xx in 15 min"
    description: >
      What it means and where to look first: the errors dashboard, the service's logs at
      Warning and above, the last deploy. This is the first responder's runbook.
  notification_settings: { receiver: acme-email }
  data:
    - refId: A
      datasourceUid: ${PROMETHEUS_DS_UID}
      relativeTimeRange: { from: 900, to: 0 }
      model:
        instant: true
        expr: sum by (service_name) (increase(http_server_request_duration_seconds_count{service_namespace="acme", http_response_status_code=~"5.."}[15m]))
    - refId: B
      datasourceUid: __expr__
      model: { type: reduce, reducer: last, expression: A }
    - refId: C
      datasourceUid: __expr__
      model: { type: threshold, expression: B, conditions: [{ evaluator: { type: gt, params: [5] } }] }
```

## Conventions

- **Small, high-signal set.** Every rule either pages someone or gets read.
  Justify a new rule in the PR description: the failure mode, who acts, and what they do.
- **Scope every selector** with the config's scope matcher, in PromQL and LogQL
  stream selectors alike. `by (service_name)` groups and does not filter, so on a
  shared stack an unscoped rule alerts on other apps' traffic. The linter strips
  grouping clauses before it looks for the filter.
- **Datasources via placeholders** (`${PROMETHEUS_DS_UID}`, `${LOKI_DS_UID}`). The
  publisher resolves them from the config, so files work across stacks.
- **uids**: the configured prefix, kebab-case, unique (a duplicate silently
  overwrites its twin). One file per domain (`service-health`, `auth`, `messaging`,
  `telemetry-health`, …).
- **Labels**: `severity: critical|warning` plus the app label the config requires
  (alert-list panels filter on it).
- **Annotations**: `summary` is one line with `{{ $labels.* }}`. `description` says
  what it means and where to look.
- **`noDataState: OK`** on every rule. Services go idle, and idle is not an outage.

## Low traffic

With a few hundred requests a week, ratios are noise: one failed request out of
three is 33 %. Prefer absolute counts over a 15-minute window
(`increase(...[15m]) > 5`), or guard a ratio with a minimum-traffic clause:

```
(sum(increase(errors_total{<scope>}[15m])) / sum(increase(requests_total{<scope>}[15m])) > 0.2)
and on() (sum(increase(requests_total{<scope>}[15m])) >= 5)
```

## Detecting a dead service without no-data alerting

Build the expected set and subtract what is reporting:

```
(
  label_replace(vector(1), "service_name", "acme-api", "", "")
  or label_replace(vector(1), "service_name", "acme-worker", "", "")
)
unless on (service_name)
  sum by (service_name) (rate(telemetry_heartbeat_total{<scope>}[5m])) > 0
```

Use `execErrState: Alerting` on this rule, and keep `noDataState: OK`.

## Loki rules

```
sum by (service_name) (count_over_time({<scope>} | severity_text="Error" [15m]))
```

`queryType: instant` on both the data item and its model. Level fields are often
structured metadata rather than index labels (check the profile), so filter them after
the selector.

## Counters

`rate()` and `increase()` need the series to exist before the first event.
Zero-seed counters at startup (emit `0` for each expected label set). Otherwise a
restart resets the baseline and a counter that has never fired returns NoData, not 0.
Seed the counter in the same change that adds a rule on it.

## Paused rules

`isPaused: true` needs a `# paused until: <what unpauses it>` comment on the line
above. The linter enforces this so a rule cannot be parked and forgotten.

## After publishing

`alerting_manage_rules list` → every rule `health: ok`. Error means the shape or the
query is wrong. NoData means a wrong name or an unseeded counter. Firing straight after
publish means the threshold is wrong, so check it against the instant query you ran
before merging.
