#!/usr/bin/env python3
"""Validates the dashboards and alert rules before they are published.

On a shared Grafana stack several apps send the same standard metric names — every
ASP.NET Core, Go or JVM service emits `http_server_request_duration_seconds` — to the
same Prometheus. A query that does not filter to this app therefore charts, and alerts
on, every other app's traffic. Every PromQL, LogQL and TraceQL expression has to carry
the app's scope matcher (`scope` in grafana-as-code.json).

The subtle case, and the one that survives code review:

    sum by (service_name) (rate(http_server_request_duration_seconds_count[5m]))

`by (service_name)` *groups* the result; it does not *filter* it. That expression matches
every app on the stack. A substring search for "service_name" says it is fine. So this
script strips the grouping and matching clauses (`by`, `without`, `on`, `ignoring`,
`group_left`, `group_right`) before it looks for a filter.

The second class of silent failure is the rule shape. Grafana evaluates a range query as
a time series and refuses to threshold it ("only reduced data can be alerted on"). A rule
in that state is in Error, and a rule in Error looks exactly like a rule at Normal from
the outside: it never fires, and nobody is told. A rule is therefore required to be
`A` (instant query) -> `B` (reduce, last) -> `C` (threshold on B), and to name the
contact point it notifies. A rule that reaches nobody is decoration.

Checks (each one that depends on a config key is skipped, with a notice, when that key
is absent):

  1. every dashboard is valid JSON, every alert file is valid YAML;
  2. every metric selector in every PromQL expression is scoped (`scope.label` equal to
     `scope.value`, or `scope.service_label` matching `scope.service_regex`), with the
     grouping clauses removed first;
  3. every LogQL stream selector is scoped the same way;
  4. every query-type dashboard variable is itself scoped, so the picker cannot list
     other apps' services; and every `$variable` a query uses is defined by the
     dashboard or listed in `allowed_variables` (a typo renders "No data", silently);
  5. every TraceQL query matches on one of `scope.traceql_attributes`;
  6. every alert rule: instant query -> reduce(last) -> threshold; an explicit
     `noDataState` that is never `Alerting` (services idle, and absence of a service is
     detected with an expected-service list instead); `notification_settings.receiver`
     set to `contact_point.name`; the `required_rule_labels`; a datasource placeholder
     the publisher knows;
  7. dashboard uids and rule uids are present, unique (a duplicate silently overwrites
     its twin at publish time) and carry their uid prefix (prune only ever deletes
     prefixed objects, so an unprefixed one would be orphaned forever);
  8. panel gridPos fits the grid (`grid_columns`, 24) and no two panels overlap;
  9. a paused rule (`isPaused: true`) carries a `# paused until: …` comment on the line
     above, naming what unpauses it, so a rule cannot be parked and forgotten;
 10. a dashboard datasource given by name is one of `datasources`, the only names the
     publisher rewrites to `{type, uid}`.

Runs in CI and needs no Grafana credentials. What it cannot tell you is whether a query
matches anything on the live stack — a correct-looking query against a metric that is
never emitted is invisible here. That is `verify_live.py`.

    python3 scripts/lint.py [--config grafana-as-code.json]

Exit status 0 when clean, 1 with one `ERROR:` line per problem otherwise. Needs PyYAML
for the alert rules (python3 -m pip install pyyaml); dashboards alone need only stdlib.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import grafana_config  # noqa: E402

EXPRESSION_DATASOURCE = "__expr__"

# Dashboard datasource names that hold logs, used when the config does not name the Loki
# datasource; their `expr` is LogQL, not PromQL.
LOGS_DATASOURCE_MARKERS = ("-logs", "loki")

# Datasource references Grafana resolves itself; never a name the publisher must rewrite.
BUILTIN_DATASOURCES = frozenset({"-- Grafana --", "-- Mixed --", "-- Dashboard --", "grafana", EXPRESSION_DATASOURCE})

# Grouping and matching clauses name labels; they never filter on them. Removed before the
# scope check so `sum by (service_name)` cannot pass for `{service_name="..."}`.
GROUPING_CLAUSE = re.compile(
    r"\b(?:by|without|on|ignoring|group_left|group_right)\s*\([^)]*\)", re.IGNORECASE
)

# A LogQL stream selector: the `{...}` block that opens a log query.
STREAM_SELECTOR = re.compile(r"\{[^}]*\}")

# Template-variable references in their three Grafana spellings: $name, ${name[:fmt]},
# [[name]]. `(?!\d)` leaves label_replace's `$1` alone.
VARIABLE_REFERENCE = re.compile(
    r"\$\{(?!\d)(\w+)(?:[:.][^}]*)?\}|\$(?!\d)(\w+)|\[\[(?!\d)(\w+)(?::\w+)?\]\]"
)

# Anything that can appear where a metric name can appear but is not one. Without this a
# selector scan reads `bool` and `offset` as unscoped metrics. (Function names followed by
# `(` are skipped separately, so this list does not need every function.)
PROMQL_KEYWORDS = frozenset(
    """
    abs absent absent_over_time acos acosh and asin asinh atan atan2 atanh avg
    avg_over_time bool bottomk ceil changes clamp clamp_max clamp_min cos cosh count
    count_over_time count_values day_of_month day_of_week day_of_year days_in_month deg
    delta deriv end exp floor group group_left group_right histogram_avg histogram_count
    histogram_fraction histogram_quantile histogram_stddev histogram_stdvar histogram_sum
    holt_winters hour idelta ignoring increase inf instant irate label_join label_replace
    last_over_time le limitk limit_ratio ln log10 log2 mad_over_time max max_over_time min
    min_over_time minute month nan offset on or pi predict_linear present_over_time
    quantile quantile_over_time rad rate resets round scalar sgn sin sinh sort sort_desc
    sqrt start stddev stddev_over_time stdvar stdvar_over_time sum sum_over_time tan tanh
    time timestamp topk unless vector without year
    """.split()
)

# A metric name, optionally followed by a label matcher block, or a matcher block with no
# name in front of it (`{__name__=~"..."}`). `(?<![\w.$])` stops a name matching the tail
# of a number (`1e6`), a duration (`5m`), a dotted attribute or a `$variable`.
SELECTOR = re.compile(r"(?<![\w.$])([A-Za-z_][\w:]*)\s*(\{[^}]*\})?|(\{[^}]*\})")


def normalize_variables(expr: str) -> str:
    """`${name}`, `${name:csv}` and `[[name]]` become `$name`.

    The braces in `${service}` would otherwise end a `{...}` matcher block early and make
    `{service_name=~"${service}"}` look unscoped.
    """
    def plain(match: re.Match) -> str:
        return "$" + next(group for group in match.groups() if group)

    return VARIABLE_REFERENCE.sub(plain, expr)


def variable_names(text: str) -> set[str]:
    return {next(g for g in m.groups() if g) for m in VARIABLE_REFERENCE.finditer(text or "")}


def mask_string_literals(expr: str) -> str:
    """Blanks quoted strings that sit outside `{...}` matcher blocks.

    `label_replace(vector(1), "service_name", "shop-web", "", "")` builds an
    expected-service list; its literals are values, not selectors, and must not be read as
    bare metric names. LogQL's `line_format "{{.msg}}"` must not be read as a stream
    selector. Strings inside matcher blocks are label values and stay put.
    """
    out: list[str] = []
    depth = 0
    i = 0
    while i < len(expr):
        char = expr[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        elif char in "\"`" and depth == 0:
            end = i + 1
            while end < len(expr) and expr[end] != char:
                end += 2 if expr[end] == "\\" and char == '"' else 1
            if end >= len(expr):
                break
            out.append(char * 2)
            i = end + 1
            continue
        out.append(char)
        i += 1
    return "".join(out)


def iter_selectors(expr: str):
    """(metric name or None, matcher block) for every series selector in a PromQL expression.

    Grouping clauses, string literals, keywords and function calls are removed first, so
    what is left is exactly the set of selectors that read series from the datasource.
    """
    stripped = GROUPING_CLAUSE.sub(" ", mask_string_literals(normalize_variables(expr)))
    for match in SELECTOR.finditer(stripped):
        if match.group(3):
            yield None, match.group(3)
            continue
        name, matchers = match.group(1), match.group(2) or ""
        if name.lower() in PROMQL_KEYWORDS:
            continue
        # A bare word followed by `(` is a function this list does not know about, and
        # guessing is worse than skipping.
        if not matchers and re.match(r"\s*\(", stripped[match.end():]):
            continue
        yield name, matchers


def label_matchers(matchers: str, label: str) -> list[tuple[str, str]]:
    """(operator, value) for every positive matcher on `label`; `!=` and `!~` never scope."""
    pattern = re.compile(r"(?<![\w.])" + re.escape(label) + r'\s*(=~|=)\s*"((?:[^"\\]|\\.)*)"')
    return [(m.group(1), m.group(2)) for m in pattern.finditer(matchers)]


def regex_alternatives(value: str) -> list[str]:
    """Top-level `|` alternatives of a regex value: `a|b(c|d)` -> ['a', 'b(c|d)']."""
    parts, depth, current = [], 0, []
    for char in value:
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        if char == "|" and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def walk_panels(node) -> list:
    """Flattens panels, including those nested inside collapsed rows."""
    found = []
    if isinstance(node, dict):
        for panel in node.get("panels", []) or []:
            found.append(panel)
            found.extend(walk_panels(panel))
    return found


def variable_query_text(variable: dict) -> str:
    query = variable.get("query")
    if isinstance(query, dict):
        query = query.get("query") or query.get("stream") or ""
    return query or variable.get("definition", "") or ""


def label_values_selector(query: str) -> str | None:
    """The selector inside `label_values(selector, label)`; None for `label_values(label)`.

    `query_result(expr)` yields its expression; anything else is returned as written.
    """
    text = query.strip()
    match = re.match(r"label_values\s*\((.*)\)\s*$", text, re.DOTALL)
    if match:
        inner = match.group(1)
        if "," not in inner:
            return None
        return inner.rsplit(",", 1)[0]
    match = re.match(r"query_result\s*\((.*)\)\s*$", text, re.DOTALL)
    if match:
        return match.group(1)
    return text


class Linter:
    def __init__(self, config: grafana_config.Config) -> None:
        self.config = config
        self.scope = config.scope
        self.problems: list[str] = []
        loki_name = config.datasources.get("loki")
        self.loki_names = {n for n in (loki_name, config.placeholder_for("loki")) if n}

    def report(self, message: str) -> None:
        self.problems.append(message)

    # -- scoping --------------------------------------------------------------------------

    def variables_ok(self, value: str, defined: set[str] | None) -> bool:
        """A matcher value built from variables is scoped if every variable is known.

        A dashboard variable resolves at query time; check_variables covers the query
        behind it. Without `allowed_variables` this trusts the variable, as Grafana would.
        """
        if self.config.allowed_variables is None:
            return True
        known = set(self.config.allowed_variables) | (defined or set())
        return variable_names(value) <= known

    def is_scoped(self, matchers: str, defined: set[str] | None = None) -> bool:
        """True when a selector's label matchers pin the series to this app."""
        scope = self.scope
        if scope is None:
            return True

        if scope.label:
            for operator, value in label_matchers(matchers, scope.label):
                if "$" in value:
                    return self.variables_ok(value, defined)
                if operator == "=":
                    return value == scope.value
                return all(alt == scope.value for alt in regex_alternatives(value))

        if scope.service_label:
            for operator, value in label_matchers(matchers, scope.service_label):
                if "$" in value:
                    return self.variables_ok(value, defined)
                alternatives = [value] if operator == "=" else regex_alternatives(value)
                return all(re.fullmatch(scope.service_regex, alt) for alt in alternatives)

        return False

    def unscoped_message(self, where: str, what: str, expr: str) -> str:
        return (
            f"{where}: {what} is not scoped to this app. Add {self.scope.describe()} — on a "
            f"shared stack, grouping by a label (`by (...)`) does not filter.\n    {expr.strip()}"
        )

    def check_expression(self, where: str, expr: str, defined: set[str] | None = None) -> int:
        """Every metric selector in a PromQL `expr` must be scoped; returns selectors seen."""
        seen = 0
        for name, matchers in iter_selectors(expr):
            seen += 1
            if self.scope is not None and not self.is_scoped(matchers, defined):
                what = f"`{name}`" if name else f"selector `{matchers}`"
                self.report(self.unscoped_message(where, what, expr))
        return seen

    def check_logql(self, where: str, expr: str, defined: set[str] | None = None) -> None:
        """Every LogQL stream selector must be scoped."""
        if self.scope is None:
            return
        selectors = STREAM_SELECTOR.findall(mask_string_literals(normalize_variables(expr)))
        if not selectors:
            self.report(f"{where}: LogQL has no stream selector, so it reads every app's logs.\n    {expr.strip()}")
            return
        for selector in selectors:
            if not self.is_scoped(selector, defined):
                self.report(self.unscoped_message(where, "LogQL stream selector", expr))

    def check_traceql(self, where: str, query: str) -> None:
        attributes = self.scope.traceql_attributes if self.scope else ()
        if not attributes:
            return
        positive = re.compile(r"(?:%s)\s*(?:=~|=)(?!=)" % "|".join(re.escape(a) for a in attributes))
        if not positive.search(query):
            self.report(
                f"{where}: TraceQL does not match on any of {list(attributes)}, so it searches "
                f"every app's traces.\n    {query.strip()}"
            )

    def check_variable_references(self, where: str, text: str, defined: set[str]) -> None:
        allowed = self.config.allowed_variables
        if allowed is None:
            return
        unknown = sorted(variable_names(text) - defined - set(allowed))
        for name in unknown:
            self.report(
                f"{where}: ${name} is neither a variable of this dashboard nor in "
                "allowed_variables — Grafana leaves it unresolved and the panel shows No data."
            )

    # -- dashboards -----------------------------------------------------------------------

    def is_logs_datasource(self, datasource) -> bool:
        """True for a Loki datasource reference, whether given by name or as {type, uid}."""
        if isinstance(datasource, dict):
            if datasource.get("type") == "loki" or datasource.get("uid") in self.loki_names:
                return True
            datasource = f"{datasource.get('uid', '')} {datasource.get('type', '')}"
        text = str(datasource or "")
        if text in self.loki_names:
            return True
        return any(marker in text.lower() for marker in LOGS_DATASOURCE_MARKERS)

    def check_panel(self, dashboard_name: str, panel: dict, defined: set[str] | None = None) -> int:
        """Checks every target of one panel; returns the number of queries checked."""
        defined = defined or set()
        title = f"{dashboard_name} / {panel.get('title', panel.get('id'))}"
        checked = 0

        for target in panel.get("targets", []) or []:
            if not isinstance(target, dict):
                continue

            datasource = target.get("datasource") or panel.get("datasource")

            if target.get("expr"):
                self.check_variable_references(title, target["expr"], defined)
                if self.is_logs_datasource(datasource):
                    self.check_logql(title, target["expr"], defined)
                else:
                    self.check_expression(title, target["expr"], defined)
                checked += 1

            if target.get("query") and isinstance(target["query"], str):
                self.check_variable_references(title, target["query"], defined)
                self.check_traceql(title, target["query"])
                checked += 1

        return checked

    def check_variables(self, file_name: str, dashboard: dict, defined: set[str]) -> None:
        for variable in dashboard.get("templating", {}).get("list", []) or []:
            if variable.get("type") != "query":
                continue
            where = f"{file_name} / variable ${variable.get('name')}"
            query = variable_query_text(variable)
            self.check_variable_references(where, query, defined)
            if self.scope is None:
                continue

            unscoped = f"{where}: the values query is not scoped, so the picker lists other apps' values too.\n    {query}"
            if self.is_logs_datasource(variable.get("datasource")):
                selector = label_values_selector(query)
                if not selector or not STREAM_SELECTOR.search(selector):
                    self.report(unscoped)
                else:
                    self.check_logql(where, selector, defined)
                continue

            selector = label_values_selector(query)
            before = len(self.problems)
            if selector is None or self.check_expression(where, selector, defined) == 0:
                self.report(unscoped)
            elif len(self.problems) > before:
                # Replace the generic selector message with the picker-specific one.
                del self.problems[before:]
                self.report(unscoped)

    def check_grid(self, file_name: str, panels: list) -> None:
        """`grid_columns` wide, positive sizes, no two panels claiming the same cell."""
        columns = self.config.grid_columns
        occupied: dict[tuple[int, int], str] = {}

        for panel in panels:
            pos = panel.get("gridPos")
            title = panel.get("title", panel.get("id"))
            if not pos:
                continue

            x, y, w, h = pos.get("x", 0), pos.get("y", 0), pos.get("w", 0), pos.get("h", 0)

            if w <= 0 or h <= 0:
                self.report(f"{file_name} / {title}: gridPos has a zero or negative size {pos}.")
                continue
            if x < 0 or x + w > columns:
                self.report(f"{file_name} / {title}: gridPos spans outside the {columns}-column grid {pos}.")
                continue

            for row in range(y, y + h):
                for column in range(x, x + w):
                    clash = occupied.get((row, column))
                    if clash is not None and clash != title:
                        self.report(f"{file_name} / {title}: overlaps '{clash}' at column {column}, row {row}.")
                        return
                    occupied[(row, column)] = title

    def check_datasource_names(self, file_name: str, node) -> None:
        """A datasource given by name must be one the publisher resolves."""
        names = set(self.config.datasources.values())
        if not names:
            return
        unknown: set[str] = set()

        def visit(value) -> None:
            if isinstance(value, dict):
                ds = value.get("datasource")
                if isinstance(ds, str) and ds not in names and ds not in BUILTIN_DATASOURCES and "$" not in ds:
                    unknown.add(ds)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(node)
        for name in sorted(unknown):
            self.report(
                f"{file_name}: datasource '{name}' is not one of the configured datasources "
                f"{sorted(names)}, so the publisher cannot resolve it to a uid."
            )

    def lint_dashboard(self, file_name: str, dashboard: dict, uids: dict[str, str]) -> int:
        uid = dashboard.get("uid")
        prefix = self.config.dashboard_uid_prefix
        if not uid:
            self.report(f"{file_name}: no uid — every publish would create a new copy instead of updating it.")
        elif uid in uids:
            self.report(f"{file_name}: uid '{uid}' is already used by {uids[uid]} — publishing would overwrite it.")
        else:
            uids[uid] = file_name
            if prefix and not uid.startswith(prefix):
                self.report(
                    f"{file_name}: uid '{uid}' does not start with '{prefix}' — --prune only "
                    "removes prefixed dashboards, so this one could never be cleaned up."
                )

        defined = {v.get("name") for v in dashboard.get("templating", {}).get("list", []) or [] if v.get("name")}

        self.check_grid(file_name, dashboard.get("panels", []) or [])
        self.check_variables(file_name, dashboard, defined)
        self.check_datasource_names(file_name, dashboard)

        checked = 0
        for panel in walk_panels(dashboard):
            checked += self.check_panel(file_name, panel, defined)
        return checked

    def lint_dashboards(self, directory: pathlib.Path) -> tuple[int, int]:
        """(dashboards, queries) checked."""
        if not directory.is_dir():
            self.report(f"dashboards_dir {directory} does not exist.")
            return 0, 0
        uids: dict[str, str] = {}
        files = queries = 0
        for path in sorted(directory.glob("*.json")):
            try:
                dashboard = json.loads(path.read_text())
            except json.JSONDecodeError as error:
                self.report(f"{path.name} is not valid JSON: {error}")
                continue
            files += 1
            queries += self.lint_dashboard(path.name, dashboard, uids)
        return files, queries

    # -- alert rules ----------------------------------------------------------------------

    def alert_query_kind(self, name: str, datasource: str | None) -> str | None:
        """'prometheus' or 'loki' for an alert query's datasourceUid; None after reporting."""
        if self.config.placeholders:
            kind = self.config.placeholders.get(datasource)
            if kind is None:
                self.report(
                    f"{name}: datasourceUid '{datasource}' is not a configured placeholder "
                    f"{sorted(self.config.placeholders)} — the publisher would refuse it."
                )
                return None
        else:
            kind = "loki" if "loki" in str(datasource or "").lower() else "prometheus"
        if kind not in ("prometheus", "loki"):
            self.report(f"{name}: alert queries must be Prometheus or Loki, not {kind}.")
            return None
        return kind

    def check_rule(self, name: str, rule: dict) -> int:
        """Shape, routing, labels, no-data policy and scoping of one rule; returns queries checked."""
        checked = 0

        no_data = rule.get("noDataState")
        if no_data is None:
            self.report(f"{name}: noDataState must be set explicitly.")
        elif no_data == "Alerting":
            self.report(
                f"{name}: noDataState Alerting is not allowed. Services idle to zero traffic, "
                "so silence is normal; detect a missing service with an expected-service list "
                "(`label_replace(vector(1), ...) unless on (service) heartbeat`), not with no-data."
            )

        contact_point = self.config.contact_point
        if contact_point is not None:
            receiver = (rule.get("notification_settings") or {}).get("receiver")
            if receiver != contact_point.name:
                self.report(
                    f"{name}: notification_settings.receiver must be '{contact_point.name}' (the "
                    "contact point publish_alerts.py provisions) — a rule without a receiver reaches nobody."
                )

        labels = rule.get("labels") or {}
        for key, value in self.config.required_rule_labels.items():
            if labels.get(key) != value:
                self.report(f"{name}: label {key}: {value} is required on every rule (found {labels.get(key)!r}).")

        by_ref = {query.get("refId"): query for query in rule.get("data", []) or [] if isinstance(query, dict)}
        threshold = by_ref.get(rule.get("condition"))
        if threshold is None or (threshold.get("model") or {}).get("type") != "threshold":
            self.report(f"{name}: condition '{rule.get('condition')}' must name a threshold expression.")
            return checked

        reducer = by_ref.get(threshold["model"].get("expression"))
        if reducer is None or (reducer.get("model") or {}).get("type") != "reduce":
            self.report(
                f"{name}: the threshold must read a reduce step (type: reduce, reducer: last), "
                "not the query directly — Grafana rejects time-series input with "
                "'only reduced data can be alerted on'."
            )
            # Still check the query the threshold reads, so one run reports every problem.
            if reducer is None or reducer.get("datasourceUid") == EXPRESSION_DATASOURCE:
                return checked
            query = reducer
        else:
            if reducer["model"].get("reducer") != "last":
                self.report(f"{name}: the reduce step must use reducer: last, not {reducer['model'].get('reducer')!r}.")
            query = by_ref.get(reducer["model"].get("expression"))
            if query is None or query.get("datasourceUid") == EXPRESSION_DATASOURCE:
                self.report(f"{name}: the reduce step must read the datasource query.")
                return checked

        model = query.get("model") or {}
        kind = self.alert_query_kind(name, query.get("datasourceUid"))
        if kind == "loki":
            if model.get("queryType") != "instant" or query.get("queryType") != "instant":
                self.report(f"{name}: a Loki alert query needs queryType: instant on both the query and its model.")
            if model.get("expr"):
                self.check_logql(name, model["expr"])
                checked += 1
        elif kind == "prometheus":
            if model.get("instant") is not True:
                self.report(
                    f"{name}: the Prometheus query needs `instant: true` — a range result is a "
                    "time series and cannot be thresholded."
                )
            if model.get("expr"):
                self.check_expression(name, model["expr"])
                checked += 1

        return checked

    PAUSED = re.compile(r"^\s*isPaused:\s*true\s*(#.*)?$", re.IGNORECASE)
    PAUSED_MARKER = "# paused until:"

    def check_paused_markers(self, file_name: str, text: str) -> None:
        """Every `isPaused: true` needs a `# paused until: …` line directly above it."""
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if not self.PAUSED.match(line):
                continue
            above = lines[index - 1].strip() if index > 0 else ""
            if not above.lower().startswith(self.PAUSED_MARKER):
                self.report(
                    f"{file_name}:{index + 1}: a paused rule needs a '{self.PAUSED_MARKER} …' comment "
                    "on the line above, naming what unpauses it."
                )

    def lint_alerts(self, directory: pathlib.Path) -> tuple[int, int]:
        """(rules, expressions) checked."""
        if not directory.is_dir():
            self.report(f"alerts_dir {directory} does not exist.")
            return 0, 0
        files = sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))
        if not files:
            return 0, 0
        try:
            import yaml
        except ImportError:
            self.report("PyYAML is required to lint the alert rules: python3 -m pip install pyyaml")
            return 0, 0

        rules = expressions = 0
        uids: dict[str, str] = {}
        prefix = self.config.rule_uid_prefix

        for path in files:
            text = path.read_text()
            self.check_paused_markers(path.name, text)
            try:
                document = yaml.safe_load(text)
            except yaml.YAMLError as error:
                self.report(f"{path.name} is not valid YAML: {error}")
                continue

            for group in (document or {}).get("groups", []) or []:
                for rule in group.get("rules", []) or []:
                    uid = rule.get("uid")
                    name = f"{path.name} / {rule.get('title', uid)}"
                    rules += 1

                    if not uid:
                        self.report(f"{name}: no uid — the publisher upserts by uid.")
                    elif uid in uids:
                        self.report(f"{name}: uid '{uid}' is already used by {uids[uid]}.")
                    else:
                        uids[uid] = name
                        if prefix and not uid.startswith(prefix):
                            self.report(
                                f"{name}: uid '{uid}' does not start with '{prefix}' — --prune and "
                                "verify_live only recognise prefixed rules as this app's."
                            )

                    expressions += self.check_rule(name, rule)

        return rules, expressions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="path to grafana-as-code.json (default: $GRAFANA_AS_CODE_CONFIG, "
                                         "else the nearest one walking up from the working directory)")
    args = parser.parse_args(argv)

    config = grafana_config.load(args.config)
    grafana_config.print_notices(
        config, "scope", "traceql", "allowed_variables", "datasources", "placeholders",
        "contact_point", "required_rule_labels", "dashboard_uid_prefix", "rule_uid_prefix",
    )

    linter = Linter(config)
    dashboards, queries = linter.lint_dashboards(config.dashboards_dir)
    rules, expressions = linter.lint_alerts(config.alerts_dir)

    if linter.problems:
        for problem in linter.problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        print(f"\n{len(linter.problems)} problem(s) found.", file=sys.stderr)
        return 1

    print(f"OK — {dashboards} dashboard(s) with {queries} queries and {rules} alert rule(s) with "
          f"{expressions} expressions pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
