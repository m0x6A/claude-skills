#!/usr/bin/env python3
"""Checks the published dashboards and alert rules against the live stack.

`lint.py` proves a query is well-formed and scoped. It cannot prove the query matches
anything, and that is the failure that sits unnoticed longest: a panel asking for
`http_server_request_duration_count` when the series is
`http_server_request_duration_seconds_count` (the OTLP -> Prometheus translation appends
the unit and `_total`), or filtering `service_name="Shop.Checkout.Api"` when the resource
attribute is `shop-checkout-api`. Both parse. Both scope correctly. Both render an empty
panel forever, and an empty panel nobody looks at is an empty panel nobody notices.

Two kinds of check, with different consequences:

  --alerts-only   Every rule in the repository must be present on the stack, and none of
                  this app's rules may report an evaluation error. A rule in Error looks
                  exactly like a rule at Normal from the outside — it never fires — so this
                  is BLOCKING: exit 1. "This app's rules" are those whose uid starts with
                  `rule_uid_prefix`, or, without one, those whose uid is in the repository.
  --panels-only   Is every metric name referenced in the dashboards and rules one the stack
                  has stored in the lookback window, every literal `scope.service_label`
                  value a real label value, and every TraceQL query one Tempo accepts?
                  ADVISORY by default (exit 0): a counter that has never been incremented
                  does not exist as a series, so a brand-new metric legitimately looks
                  missing until it first fires. Pass --strict to exit non-zero.

Without either flag both run; the exit code is 1 if the alert check fails (or, with
--strict, if any reference is missing). The panel check needs `datasources.prometheus`
(and `datasources.tempo` for TraceQL); without them that part is skipped with a notice.

Run --alerts-only after a publish, once Grafana has had one evaluation interval to
evaluate the rules it just received; before that a new rule has no health to report.

    export GRAFANA_URL="https://<stack>.grafana.net"
    export GRAFANA_API_TOKEN="<service-account token: Viewer is enough>"
    python3 scripts/verify_live.py [--alerts-only|--panels-only] [--strict] [--lookback 30d]
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import grafana_config  # noqa: E402
import lint  # noqa: E402

UNHEALTHY = {"err", "error"}

UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_lookback(value: str) -> float:
    match = re.fullmatch(r"(\d+)([smhdw])", value.strip())
    if match is None:
        sys.exit(f"--lookback must look like 30d or 12h, not {value!r}")
    return int(match.group(1)) * UNITS[match.group(2)]


def request(base: str, token: str, path: str) -> tuple[int, dict | list | str]:
    """Status and decoded body; a 4xx is data here (a rejected TraceQL query is a finding)."""
    req = urllib.request.Request(f"{base}{path}", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace")[:400]
        try:
            return error.code, json.loads(body)
        except json.JSONDecodeError:
            return error.code, body


def api(base: str, token: str, path: str) -> dict:
    status, body = request(base, token, path)
    if status >= 400:
        sys.exit(f"ERROR {status} on {path}: {body}")
    return body


def load_yaml(path: pathlib.Path) -> dict:
    try:
        import yaml
    except ImportError:
        sys.exit("PyYAML is required: python3 -m pip install pyyaml")
    return yaml.safe_load(path.read_text()) or {}


def alert_paths(config: grafana_config.Config) -> list[pathlib.Path]:
    if not config.alerts_dir.is_dir():
        return []
    return sorted(config.alerts_dir.glob("*.yaml")) + sorted(config.alerts_dir.glob("*.yml"))


def dashboard_paths(config: grafana_config.Config) -> list[pathlib.Path]:
    if not config.dashboards_dir.is_dir():
        return []
    return sorted(config.dashboards_dir.glob("*.json"))


def collect_references(config: grafana_config.Config) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """metric name -> where it is used, and literal service-label value -> where."""
    linter = lint.Linter(config)
    service_label = config.scope.service_label if config.scope else None
    metrics: dict[str, set[str]] = {}
    services: dict[str, set[str]] = {}

    def scan(where: str, expr: str) -> None:
        for name, matchers in lint.iter_selectors(expr):
            if name:
                metrics.setdefault(name, set()).add(where)
            if service_label:
                for operator, value in lint.label_matchers(matchers, service_label):
                    if operator == "=" and "$" not in value:
                        services.setdefault(value, set()).add(where)

    for path in dashboard_paths(config):
        dashboard = json.loads(path.read_text())
        for panel in lint.walk_panels(dashboard):
            title = f"{path.name} / {panel.get('title', panel.get('id'))}"
            for target in panel.get("targets", []) or []:
                if not isinstance(target, dict) or not target.get("expr"):
                    continue
                if linter.is_logs_datasource(target.get("datasource") or panel.get("datasource")):
                    continue  # LogQL: its stream selector is labels, not a metric name
                scan(title, target["expr"])
        for variable in dashboard.get("templating", {}).get("list", []) or []:
            if variable.get("type") != "query" or linter.is_logs_datasource(variable.get("datasource")):
                continue
            selector = lint.label_values_selector(lint.variable_query_text(variable))
            if selector:
                scan(f"{path.name} / variable ${variable.get('name')}", selector)

    loki_placeholder = config.placeholder_for("loki")
    for path in alert_paths(config):
        for group in load_yaml(path).get("groups", []) or []:
            for rule in group.get("rules", []) or []:
                name = f"{path.name} / {rule.get('title', rule.get('uid'))}"
                for query in rule.get("data", []) or []:
                    expr = (query.get("model") or {}).get("expr")
                    if not expr or query.get("datasourceUid") == lint.EXPRESSION_DATASOURCE:
                        continue
                    datasource = str(query.get("datasourceUid") or "")
                    if datasource == loki_placeholder or (not loki_placeholder and "loki" in datasource.lower()):
                        continue  # LogQL: its stream selector is labels, not a metric name
                    scan(name, expr)

    return metrics, services


def collect_traceql(config: grafana_config.Config) -> list[tuple[str, str]]:
    """(where, query) for every TraceQL panel target."""
    found: list[tuple[str, str]] = []
    for path in dashboard_paths(config):
        dashboard = json.loads(path.read_text())
        for panel in lint.walk_panels(dashboard):
            title = f"{path.name} / {panel.get('title', panel.get('id'))}"
            for target in panel.get("targets", []) or []:
                if isinstance(target, dict) and isinstance(target.get("query"), str) and target["query"]:
                    found.append((title, target["query"]))
    return found


def repo_rule_uids(config: grafana_config.Config) -> set[str]:
    uids: set[str] = set()
    for path in alert_paths(config):
        for group in load_yaml(path).get("groups", []) or []:
            for rule in group.get("rules", []) or []:
                if rule.get("uid"):
                    uids.add(rule["uid"])
    return uids


def live_rules(payload: dict) -> list[dict]:
    rules: list[dict] = []
    for group in (payload.get("data") or {}).get("groups", []) or []:
        rules.extend(group.get("rules", []) or [])
    return rules


def is_ours(uid: str, prefix: str | None, repo_uids: set[str]) -> bool:
    return uid.startswith(prefix) if prefix else uid in repo_uids


def alert_health_problems(payload: dict, prefix: str | None, repo_uids: set[str]) -> list[dict]:
    """This app's rules whose last evaluation errored, with Grafana's reason."""
    return [
        {
            "uid": rule.get("uid"),
            "name": rule.get("name"),
            "health": rule.get("health"),
            "error": rule.get("lastError", ""),
        }
        for rule in live_rules(payload)
        if is_ours(str(rule.get("uid", "")), prefix, repo_uids)
        and str(rule.get("health", "")).lower() in UNHEALTHY
    ]


def missing_rules(payload: dict, expected_uids: set[str]) -> list[str]:
    present = {rule.get("uid") for rule in live_rules(payload)}
    return sorted(uid for uid in expected_uids if uid not in present)


def check_alerts(base: str, token: str, config: grafana_config.Config) -> bool:
    payload = api(base, token, "/api/prometheus/grafana/api/v1/rules")
    repo_uids = repo_rule_uids(config)
    problems = alert_health_problems(payload, config.rule_uid_prefix, repo_uids)
    absent = missing_rules(payload, repo_uids)

    for problem in problems:
        print(f"RULE IN ERROR   {problem['uid']} ({problem['name']}): {problem['error']}")
    for uid in absent:
        print(f"RULE MISSING    {uid} is in the repository but Grafana is not evaluating it")

    if problems or absent:
        print(f"\n{len(problems)} rule(s) in Error, {len(absent)} missing.")
        return False

    evaluated = sum(
        1 for r in live_rules(payload)
        if is_ours(str(r.get("uid", "")), config.rule_uid_prefix, repo_uids)
    )
    print(f"OK — {evaluated} alert rules are evaluating without error.")
    return True


def near_matches(name: str, known: set[str]) -> list[str]:
    """Known values that look like `name` once case and separators are ignored."""
    def squash(text: str) -> str:
        return re.sub(r"[^a-z0-9]", "", text.lower())

    target = squash(name)
    return sorted(value for value in known if target and (target in squash(value) or squash(value) in target))


def check_panels(base: str, token: str, config: grafana_config.Config, lookback: str, strict: bool) -> bool:
    prom_name = config.datasources.get("prometheus")
    if not prom_name:
        print("notice: datasources.prometheus is not set: the panel check is skipped.", file=sys.stderr)
        return True

    prom = api(base, token, f"/api/datasources/name/{urllib.parse.quote(prom_name, safe='')}")
    proxy = f"/api/datasources/proxy/uid/{prom['uid']}/api/v1"

    # The Prometheus HTTP API takes unix seconds or RFC3339, not Grafana's relative syntax.
    now = time.time()
    start = now - parse_lookback(lookback)
    window = urllib.parse.urlencode({"start": f"{start:.0f}", "end": f"{now:.0f}"})

    metrics, services = collect_references(config)

    known_metrics = set(api(base, token, f"{proxy}/label/__name__/values?{window}")["data"])
    missing_metrics = {n: w for n, w in metrics.items() if n not in known_metrics}

    missing_services: dict[str, set[str]] = {}
    known_services: set[str] = set()
    service_label = config.scope.service_label if config.scope else None
    if service_label and services:
        label = urllib.parse.quote(service_label, safe="")
        known_services = set(api(base, token, f"{proxy}/label/{label}/values?{window}")["data"])
        missing_services = {n: w for n, w in services.items() if n not in known_services}

    for name, used_in in sorted(missing_metrics.items()):
        near = near_matches(name, known_metrics)[:1]
        hint = f"  (did you mean {near[0]}?)" if near else ""
        print(f"MISSING METRIC  {name}{hint}")
        for where in sorted(used_in):
            print(f"                  used by {where}")

    for name, used_in in sorted(missing_services.items()):
        near = near_matches(name, known_services)[:1]
        hint = f"  (did you mean {near[0]}?)" if near else ""
        print(f"MISSING {service_label.upper()} {name!r}{hint}")
        for where in sorted(used_in):
            print(f"                  used by {where}")

    # TraceQL: Tempo either accepts the query (possibly with no series yet) or rejects it.
    rejected = 0
    empty = 0
    queries = collect_traceql(config)
    tempo_name = config.datasources.get("tempo")
    if queries and not tempo_name:
        print(f"notice: datasources.tempo is not set: {len(queries)} TraceQL queries are not checked.",
              file=sys.stderr)
        queries = []
    if queries:
        tempo = api(base, token, f"/api/datasources/name/{urllib.parse.quote(tempo_name, safe='')}")
        tempo_proxy = f"/api/datasources/proxy/uid/{tempo['uid']}/api/metrics/query"
        for where, query in queries:
            params = urllib.parse.urlencode({"q": query, "start": f"{now - 86400:.0f}", "end": f"{now:.0f}"})
            status, body = request(base, token, f"{tempo_proxy}?{params}")
            if status >= 400:
                rejected += 1
                print(f"TRACEQL REJECTED {where}: {str(body)[:200]}\n                  {query}")
            elif not (isinstance(body, dict) and body.get("series")):
                empty += 1
                print(f"TRACEQL EMPTY   {where} (no series in the last 24 h)")

    total = len(missing_metrics) + len(missing_services) + rejected
    checked = len(metrics) + len(services) + len(queries)

    if total == 0:
        print(f"OK — all {checked} referenced series, service names and TraceQL queries resolve "
              f"in the last {lookback} ({empty} TraceQL panels had no series in 24 h).")
        return True

    print(
        f"\n{total} of {checked} references match nothing in the last {lookback}.\n"
        "A counter that has never been incremented is not stored, so a genuinely new metric\n"
        "shows up here until it first fires. Anything else is a panel that will never fill."
    )
    return not strict


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="path to grafana-as-code.json")
    only = parser.add_mutually_exclusive_group()
    only.add_argument("--alerts-only", action="store_true", help="only check alert-rule health (blocking)")
    only.add_argument("--panels-only", action="store_true", help="only check dashboard/alert references (advisory)")
    parser.add_argument("--strict", action="store_true", help="exit non-zero on any missing reference too")
    parser.add_argument("--lookback", default="30d", help="how far back to look for series (default 30d)")
    args = parser.parse_args(argv)

    config = grafana_config.load(args.config)
    if not args.panels_only:
        grafana_config.print_notices(config, "rule_uid_prefix")

    base = (os.environ.get("GRAFANA_URL") or "").rstrip("/")
    token = os.environ.get("GRAFANA_API_TOKEN")
    if not base or not token:
        sys.exit("Set GRAFANA_URL and GRAFANA_API_TOKEN.")

    ok = True
    if not args.panels_only:
        ok = check_alerts(base, token, config) and ok
    if not args.alerts_only:
        ok = check_panels(base, token, config, args.lookback, args.strict) and ok

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
