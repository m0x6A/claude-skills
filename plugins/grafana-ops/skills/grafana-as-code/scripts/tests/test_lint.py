#!/usr/bin/env python3
"""Unit tests for lint.py's scoping, alert-rule, dashboard and config-driven checks.

    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import contextlib
import copy
import io
import pathlib
import unittest

import support

import lint


def prometheus_rule() -> dict:
    return {
        "uid": "acme-example",
        "title": "Example",
        "condition": "C",
        "noDataState": "OK",
        "execErrState": "Error",
        "labels": {"severity": "warning", "app": "acme"},
        "notification_settings": {"receiver": "acme-email"},
        "data": [
            {
                "refId": "A",
                "relativeTimeRange": {"from": 600, "to": 0},
                "datasourceUid": "${PROMETHEUS_DS_UID}",
                "model": {
                    "expr": 'sum(rate(http_server_request_duration_seconds_count{service_namespace="acme"}[5m]))',
                    "instant": True,
                    "range": False,
                },
            },
            {
                "refId": "B",
                "datasourceUid": "__expr__",
                "model": {"type": "reduce", "reducer": "last", "expression": "A"},
            },
            {
                "refId": "C",
                "datasourceUid": "__expr__",
                "model": {"type": "threshold", "expression": "B", "conditions": []},
            },
        ],
    }


def loki_rule() -> dict:
    rule = prometheus_rule()
    rule["data"][0] = {
        "refId": "A",
        "relativeTimeRange": {"from": 900, "to": 0},
        "datasourceUid": "${LOKI_DS_UID}",
        "queryType": "instant",
        "model": {
            "expr": 'sum by (service_name) (count_over_time({service_namespace="acme"} | severity_text="Critical" [15m]))',
            "queryType": "instant",
        },
    }
    return rule


class LinterTestCase(unittest.TestCase):
    overrides: dict = {}
    drop: tuple[str, ...] = ()

    def setUp(self) -> None:
        self.linter = lint.Linter(support.config(self.overrides, self.drop))

    @property
    def problems(self) -> list[str]:
        return self.linter.problems

    def assert_problem(self, fragment: str) -> None:
        self.assertTrue(any(fragment in p for p in self.problems), self.problems)


class RuleShapeTests(LinterTestCase):
    def test_well_formed_prometheus_rule_passes(self) -> None:
        self.linter.check_rule("service-health.yaml / Example", prometheus_rule())
        self.assertEqual(self.problems, [])

    def test_well_formed_loki_rule_passes(self) -> None:
        self.linter.check_rule("service-health.yaml / Example", loki_rule())
        self.assertEqual(self.problems, [])

    def test_prometheus_query_without_instant_is_reported(self) -> None:
        rule = prometheus_rule()
        del rule["data"][0]["model"]["instant"]
        self.linter.check_rule("x", rule)
        self.assert_problem("instant")

    def test_loki_query_without_instant_query_type_is_reported(self) -> None:
        rule = loki_rule()
        del rule["data"][0]["model"]["queryType"]
        self.linter.check_rule("x", rule)
        self.assert_problem("instant")

    def test_threshold_reading_the_query_directly_is_reported(self) -> None:
        rule = prometheus_rule()
        rule["data"] = [rule["data"][0], copy.deepcopy(rule["data"][2])]
        rule["data"][1]["model"]["expression"] = "A"
        self.linter.check_rule("x", rule)
        self.assert_problem("only reduced data")

    def test_query_read_directly_by_the_threshold_is_still_checked(self) -> None:
        rule = prometheus_rule()
        rule["data"] = [rule["data"][0], copy.deepcopy(rule["data"][2])]
        rule["data"][1]["model"]["expression"] = "A"
        rule["data"][0]["model"] = {"expr": "sum by (service_name)(rate(x[5m]))", "range": True}
        self.linter.check_rule("x", rule)
        self.assert_problem("only reduced data")
        self.assert_problem("instant: true")
        self.assert_problem("`x` is not scoped")

    def test_reducer_other_than_last_is_reported(self) -> None:
        rule = prometheus_rule()
        rule["data"][1]["model"]["reducer"] = "mean"
        self.linter.check_rule("x", rule)
        self.assert_problem("reducer: last")

    def test_condition_not_naming_a_threshold_is_reported(self) -> None:
        rule = prometheus_rule()
        rule["condition"] = "B"
        self.linter.check_rule("x", rule)
        self.assert_problem("threshold expression")

    def test_missing_receiver_is_reported(self) -> None:
        rule = prometheus_rule()
        del rule["notification_settings"]
        self.linter.check_rule("x", rule)
        self.assert_problem("acme-email")

    def test_wrong_receiver_is_reported(self) -> None:
        rule = prometheus_rule()
        rule["notification_settings"]["receiver"] = "somebody-else"
        self.linter.check_rule("x", rule)
        self.assert_problem("acme-email")

    def test_no_data_alerting_is_reported_for_any_rule(self) -> None:
        rule = prometheus_rule()
        rule["noDataState"] = "Alerting"
        self.linter.check_rule("x", rule)
        self.assert_problem("noDataState")

    def test_missing_no_data_state_is_reported(self) -> None:
        rule = prometheus_rule()
        del rule["noDataState"]
        self.linter.check_rule("x", rule)
        self.assert_problem("noDataState must be set")

    def test_missing_required_label_is_reported(self) -> None:
        rule = prometheus_rule()
        rule["labels"]["app"] = "other"
        self.linter.check_rule("x", rule)
        self.assert_problem("label app: acme")

    def test_unknown_placeholder_is_reported(self) -> None:
        rule = prometheus_rule()
        rule["data"][0]["datasourceUid"] = "${TEMPO_DS_UID}"
        self.linter.check_rule("x", rule)
        self.assert_problem("not a configured placeholder")

    def test_expected_service_list_expression_is_scoped(self) -> None:
        rule = prometheus_rule()
        rule["data"][0]["model"]["expr"] = (
            '(label_replace(vector(1), "service_name", "acme-web", "", "") '
            'or label_replace(vector(1), "service_name", "acme-checkout", "", "")) '
            'unless on (service_name) (sum by (service_name) '
            '(rate(telemetry_heartbeat_total{service_namespace="acme"}[10m])) > 0)'
        )
        self.linter.check_rule("x", rule)
        self.assertEqual(self.problems, [])

    def test_unscoped_prometheus_expression_is_reported(self) -> None:
        rule = prometheus_rule()
        rule["data"][0]["model"]["expr"] = "sum(rate(http_server_request_duration_seconds_count[5m]))"
        self.linter.check_rule("x", rule)
        self.assert_problem("not scoped")


class RuleShapeWithoutOptionalKeysTests(LinterTestCase):
    drop = ("contact_point", "required_rule_labels", "placeholders")

    def test_receiver_and_labels_are_not_checked_without_their_keys(self) -> None:
        rule = prometheus_rule()
        del rule["notification_settings"]
        del rule["labels"]
        self.linter.check_rule("x", rule)
        self.assertEqual(self.problems, [])

    def test_without_placeholders_a_loki_uid_is_recognised_by_name(self) -> None:
        rule = loki_rule()
        rule["data"][0]["datasourceUid"] = "grafanacloud-loki-uid"
        del rule["data"][0]["queryType"]
        self.linter.check_rule("x", rule)
        self.assert_problem("Loki alert query")


class PromQlScopeTests(LinterTestCase):
    def test_grouping_by_the_service_label_is_not_a_filter(self) -> None:
        # The headline case: a substring search for service_name would pass this.
        self.linter.check_expression("x", "sum by (service_name) (rate(http_server_request_duration_seconds_count[5m]))")
        self.assertEqual(len(self.problems), 1, self.problems)
        self.assert_problem("`http_server_request_duration_seconds_count`")

    def test_on_and_ignoring_clauses_are_not_filters(self) -> None:
        self.linter.check_expression("x", 'a{service_namespace="acme"} / on (service_namespace) b')
        self.assert_problem("`b`")

    def test_service_label_matching_the_regex_scopes(self) -> None:
        self.linter.check_expression("x", 'rate(x_total{service_name="acme-web"}[5m])')
        self.linter.check_expression("x", 'rate(x_total{service_name=~"acme-web|acme-api"}[5m])')
        self.assertEqual(self.problems, [])

    def test_service_regex_alternative_outside_the_app_is_reported(self) -> None:
        self.linter.check_expression("x", 'rate(x_total{service_name=~"acme-web|other-api"}[5m])')
        self.assertEqual(len(self.problems), 1, self.problems)

    def test_wrong_namespace_value_is_reported(self) -> None:
        self.linter.check_expression("x", 'rate(x_total{service_namespace="acme-staging"}[5m])')
        self.assertEqual(len(self.problems), 1, self.problems)

    def test_negative_matcher_does_not_scope(self) -> None:
        self.linter.check_expression("x", 'rate(x_total{service_name!="acme-web"}[5m])')
        self.assertEqual(len(self.problems), 1, self.problems)

    def test_a_longer_label_ending_in_the_scope_label_does_not_scope(self) -> None:
        self.linter.check_expression("x", 'rate(x_total{k8s_service_namespace="acme"}[5m])')
        self.assertEqual(len(self.problems), 1, self.problems)

    def test_nameless_selector_is_checked(self) -> None:
        self.linter.check_expression("x", 'count({__name__=~"http_.*"})')
        self.assert_problem("selector")

    def test_dashboard_variables_are_not_read_as_metric_names(self) -> None:
        self.linter.check_expression(
            "cost",
            '(sum(increase(prompt_tokens_input_total{service_namespace="acme"}[24h])) * $price_in) / 1e6',
            {"price_in"},
        )
        self.linter.check_expression(
            "p75",
            'histogram_quantile(0.75, sum by (le) (rate(web_vitals_bucket{service_namespace="acme"}[$__range])))',
        )
        self.assertEqual(self.problems, [])

    def test_braced_variable_in_a_matcher_scopes(self) -> None:
        self.linter.check_expression("x", 'rate(x_total{service_name=~"${service:regex}"}[5m])', {"service"})
        self.assertEqual(self.problems, [])

    def test_matcher_on_an_unknown_variable_does_not_scope(self) -> None:
        self.linter.check_expression("x", 'rate(x_total{service_name=~"$anything"}[5m])', set())
        self.assertEqual(len(self.problems), 1, self.problems)


class ScopeDisabledTests(LinterTestCase):
    drop = ("scope",)

    def test_nothing_is_reported_for_scoping_without_a_scope(self) -> None:
        self.linter.check_expression("x", "sum by (service_name) (rate(x_total[5m]))")
        self.linter.check_logql("x", '{job="x"}')
        self.linter.check_traceql("x", "{ span.http.status_code >= 500 }")
        self.assertEqual(self.problems, [])


class LogQlScopeTests(LinterTestCase):
    def test_scoped_stream_selector_passes(self) -> None:
        self.linter.check_logql("x", 'sum(count_over_time({service_namespace="acme"} | severity_text="Error" [15m]))')
        self.assertEqual(self.problems, [])

    def test_service_name_scoped_stream_selector_passes(self) -> None:
        self.linter.check_logql("x", '{service_name="acme-web"} | severity_text="Error"')
        self.assertEqual(self.problems, [])

    def test_unscoped_stream_selector_is_reported(self) -> None:
        self.linter.check_logql("x", 'sum(count_over_time({severity_text="Error"}[15m]))')
        self.assertEqual(len(self.problems), 1, self.problems)

    def test_logql_without_any_stream_selector_is_reported(self) -> None:
        self.linter.check_logql("x", "sum(rate(foo[5m]))")
        self.assertEqual(len(self.problems), 1, self.problems)

    def test_line_format_template_is_not_a_stream_selector(self) -> None:
        self.linter.check_logql("x", '{service_namespace="acme"} | json | line_format "{{.message}}"')
        self.assertEqual(self.problems, [])

    def test_loki_dashboard_target_is_checked_as_logql(self) -> None:
        panel = {
            "title": "Errors",
            "datasource": "acme-logs",
            "targets": [{"expr": 'sum(count_over_time({service_namespace="acme"}[5m]))'}],
        }
        self.linter.check_panel("dash.json", panel)
        self.assertEqual(self.problems, [])


class TraceQlScopeTests(LinterTestCase):
    def test_scoped_traceql_passes(self) -> None:
        self.linter.check_traceql("x", '{ resource.service.namespace = "acme" && span.http.status_code >= 500 }')
        self.assertEqual(self.problems, [])

    def test_unscoped_traceql_is_reported(self) -> None:
        self.linter.check_traceql("x", "{ span.http.status_code >= 500 }")
        self.assertEqual(len(self.problems), 1, self.problems)

    def test_negated_attribute_does_not_scope(self) -> None:
        self.linter.check_traceql("x", '{ resource.service.name != "acme-web" }')
        self.assertEqual(len(self.problems), 1, self.problems)


class DashboardTests(LinterTestCase):
    def dashboard(self, **extra) -> dict:
        base = {
            "uid": "acme-overview",
            "templating": {"list": [{
                "type": "query",
                "name": "service",
                "datasource": "acme-prom",
                "query": {"query": 'label_values(target_info{service_namespace="acme"}, service_name)'},
            }]},
            "panels": [{
                "id": 1, "title": "Rate", "datasource": "acme-prom",
                "gridPos": {"x": 0, "y": 0, "w": 24, "h": 8},
                "targets": [{"expr": 'sum(rate(x_total{service_namespace="acme", service_name=~"$service"}[$__rate_interval]))'}],
            }],
        }
        base.update(extra)
        return base

    def test_well_formed_dashboard_passes(self) -> None:
        self.assertEqual(self.linter.lint_dashboard("d.json", self.dashboard(), {}), 1)
        self.assertEqual(self.problems, [])

    def test_unknown_variable_reference_is_reported(self) -> None:
        dashboard = self.dashboard()
        dashboard["panels"][0]["targets"][0]["expr"] = 'sum(rate(x_total{service_namespace="acme"}[$__rate_intervl]))'
        self.linter.lint_dashboard("d.json", dashboard, {})
        self.assert_problem("$__rate_intervl")

    def test_unscoped_variable_query_is_reported(self) -> None:
        dashboard = self.dashboard()
        dashboard["templating"]["list"][0]["query"] = {"query": "label_values(target_info, service_name)"}
        self.linter.lint_dashboard("d.json", dashboard, {})
        self.assert_problem("variable $service")

    def test_label_values_without_a_selector_is_reported(self) -> None:
        dashboard = self.dashboard()
        dashboard["templating"]["list"][0]["query"] = "label_values(service_name)"
        self.linter.lint_dashboard("d.json", dashboard, {})
        self.assert_problem("variable $service")

    def test_duplicate_uid_is_reported(self) -> None:
        uids: dict[str, str] = {}
        self.linter.lint_dashboard("a.json", self.dashboard(), uids)
        self.linter.lint_dashboard("b.json", self.dashboard(), uids)
        self.assert_problem("already used by a.json")

    def test_missing_uid_is_reported(self) -> None:
        dashboard = self.dashboard()
        del dashboard["uid"]
        self.linter.lint_dashboard("d.json", dashboard, {})
        self.assert_problem("no uid")

    def test_uid_without_the_prefix_is_reported(self) -> None:
        self.linter.lint_dashboard("d.json", self.dashboard(uid="overview"), {})
        self.assert_problem("does not start with 'acme-'")

    def test_unknown_datasource_name_is_reported(self) -> None:
        dashboard = self.dashboard()
        dashboard["panels"][0]["datasource"] = "some-other-stack-prom"
        self.linter.lint_dashboard("d.json", dashboard, {})
        self.assert_problem("some-other-stack-prom")

    def test_builtin_and_variable_datasources_are_accepted(self) -> None:
        self.linter.check_datasource_names("d.json", {"panels": [{"datasource": "-- Grafana --"}, {"datasource": "${ds}"}]})
        self.assertEqual(self.problems, [])

    def test_overlapping_panels_are_reported(self) -> None:
        panels = [
            {"title": "A", "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8}},
            {"title": "B", "gridPos": {"x": 6, "y": 4, "w": 12, "h": 8}},
        ]
        self.linter.check_grid("d.json", panels)
        self.assert_problem("overlaps 'A'")

    def test_panel_wider_than_the_grid_is_reported(self) -> None:
        self.linter.check_grid("d.json", [{"title": "A", "gridPos": {"x": 12, "y": 0, "w": 13, "h": 8}}])
        self.assert_problem("24-column grid")

    def test_panels_in_collapsed_rows_are_checked(self) -> None:
        dashboard = self.dashboard()
        dashboard["panels"].append({"type": "row", "title": "More", "panels": [
            {"title": "Hidden", "datasource": "acme-prom", "targets": [{"expr": "sum(rate(y_total[5m]))"}]},
        ]})
        self.linter.lint_dashboard("d.json", dashboard, {})
        self.assert_problem("`y_total`")


class VariablesUncheckedTests(LinterTestCase):
    drop = ("allowed_variables",)

    def test_variable_references_are_trusted_without_allowed_variables(self) -> None:
        self.linter.check_expression("x", 'rate(x_total{service_name=~"$anything"}[$__whatever])', set())
        self.linter.check_variable_references("x", "$__whatever", set())
        self.assertEqual(self.problems, [])


class PausedRuleMarkerTests(LinterTestCase):
    def test_paused_rule_with_marker_passes(self) -> None:
        self.linter.check_paused_markers("x.yaml", "      - uid: acme-x\n        # paused until: runbook done (#12)\n        isPaused: true\n")
        self.assertEqual(self.problems, [])

    def test_paused_rule_without_marker_is_reported(self) -> None:
        self.linter.check_paused_markers("x.yaml", "      - uid: acme-x\n        isPaused: true\n")
        self.assertEqual(len(self.problems), 1)


class EndToEndTests(unittest.TestCase):
    """lint.main() against a project built from templates/."""

    def run_main(self, root: pathlib.Path) -> tuple[int, str]:
        err = io.StringIO()
        out = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            code = lint.main(["--config", str(root / "grafana-as-code.json")])
        return code, out.getvalue() + err.getvalue()

    def test_the_templates_lint_clean_with_no_notices(self) -> None:
        code, output = self.run_main(support.project_from_templates())
        self.assertEqual(code, 0, output)
        self.assertNotIn("notice:", output)

    def test_a_range_query_thresholded_directly_and_unscoped_fails(self) -> None:
        root = support.project_from_templates()
        alert = root / "telemetry" / "grafana" / "alerts" / "example-alert.yaml"
        text = alert.read_text()
        text = text.replace(
            'sum by (service_name) (increase(http_server_request_duration_seconds_count{service_namespace="acme", http_response_status_code=~"5.."}[15m]))',
            "sum by (service_name)(rate(x[5m]))",
        ).replace("instant: true", "instant: false").replace("expression: B", "expression: A")
        alert.write_text(text)
        code, output = self.run_main(root)
        self.assertEqual(code, 1, output)
        self.assertIn("only reduced data", output)

    def test_a_minimal_config_prints_notices_and_still_lints(self) -> None:
        root = support.project_from_templates()
        support.write_json(root / "grafana-as-code.json",
                           {"dashboards_dir": "telemetry/grafana/dashboards", "alerts_dir": "telemetry/grafana/alerts"})
        code, output = self.run_main(root)
        self.assertEqual(code, 0, output)
        self.assertIn("notice: scope is not set", output)


if __name__ == "__main__":
    unittest.main()
