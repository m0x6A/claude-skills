# Dashboards: layout, variables, units, naming

## Shape of a dashboard set

Three entry points answer three questions, and everything else hangs off them:

| Dashboard | Question |
|---|---|
| system overview | Is anything wrong right now? (RED per service, heartbeat, alert list) |
| errors and logs | Where? (5xx by route, exceptions by type, Loki panel at Warning+) |
| telemetry health | Can the data be trusted? (heartbeat per service, exporter drops, rules in error) |

Then one per area (gateway, frontend, runtime and database, messaging, external
dependencies/AI) and one per bounded context or service. Link the entry points to the
area dashboards with dashboard links that carry `${__from}`/`${__to}` and the service
variable.

## Conventions the linter checks

- uid = configured prefix + filename stem; one folder per app.
- Datasources by **name** in the JSON. The publisher resolves names to `{type, uid}`,
  so files are portable across stacks.
- Every selector scoped (PromQL, LogQL stream selectors, TraceQL
  `resource.service.namespace`). Template variables that feed queries are scoped too.
- Variables in `allowed_variables` (plus built-ins) are known to the linter; add a
  new one there, not by disabling the check.
- 24-column grid, no overlapping `gridPos`.

## Conventions worth keeping (not machine-checked)

- A **Service** variable on every dashboard, fed by the heartbeat:
  `label_values(telemetry_heartbeat_total{<scope>}, service_name)` with a regex for
  the area. Surfaces with no heartbeat (the browser) get a fixed custom value.
- 30 s refresh, 6 h default range.
- A **description on every panel**: what it shows and which instrument emits it.
- Thresholds, drawn as threshold lines, on every RED panel, using the same numbers as the alert
  rules. **One error definition**: if the alert counts 5xx as `increase(...[15m])`,
  the panel does too, so the panel and the page always agree.
- Units follow the instrument: `reqps`, `short`, `s`, `ms`, `bytes`, `percentunit`.
  CPU is cores used (`rate(process_cpu_time_seconds_total[5m])`) against the
  container limit, never a host percentage.
- Overlay deploys as annotations (a Loki or Prometheus annotation query on the
  release marker) so inflections line up with releases.

## Metric names come from the stack, not the instrument

OTLP → Prometheus translation appends the unit and `_total`:
`http.server.request.duration` (s) → `http_server_request_duration_seconds_{bucket,count,sum}`;
a counter `orders.placed` → `orders_placed_total`. Some exporters append an extra suffix
(`_ea_total`). Always confirm with `gcx metrics list-names -d <prom> --contains <part>` before
you write a panel. When the browser and the backend share a counter name, add a `service_name`
matcher.

## Verifying

Offline lint catches structure. It cannot know whether a query matches anything,
so run `verify_live --panels-only` with a read token. Then look at the panels with real
data (`gcx dashboards snapshot <uid> --panel <id>`). A dashboard nobody has looked at with real data is not done.
