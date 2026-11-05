#!/usr/bin/env python3
"""Unit tests for the pure parts of verify_live.py (no network).

    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import pathlib
import tempfile
import unittest

import support

import verify_live

PAYLOAD = {
    "data": {
        "groups": [
            {
                "name": "service-health",
                "rules": [
                    {"name": "A", "uid": "acme-ok", "health": "ok"},
                    {"name": "B", "uid": "acme-broken", "health": "err", "lastError": "only reduced data"},
                    {"name": "C", "uid": "acme-quiet", "health": "nodata"},
                    {"name": "D", "uid": "neighbour-broken", "health": "err", "lastError": "x"},
                ],
            }
        ]
    }
}


class AlertHealthTests(unittest.TestCase):
    def test_only_our_rules_in_error_are_reported(self) -> None:
        problems = verify_live.alert_health_problems(PAYLOAD, "acme-", set())
        self.assertEqual([p["uid"] for p in problems], ["acme-broken"])
        self.assertIn("only reduced data", problems[0]["error"])

    def test_without_a_prefix_our_rules_are_the_ones_in_the_repository(self) -> None:
        problems = verify_live.alert_health_problems(PAYLOAD, None, {"acme-ok", "acme-broken"})
        self.assertEqual([p["uid"] for p in problems], ["acme-broken"])
        self.assertEqual(verify_live.alert_health_problems(PAYLOAD, None, {"acme-ok"}), [])

    def test_missing_rules_are_reported_when_expected(self) -> None:
        payload = {"data": {"groups": [{"rules": [{"uid": "acme-ok", "health": "ok"}]}]}}
        self.assertEqual(verify_live.missing_rules(payload, {"acme-ok", "acme-new"}), ["acme-new"])


class LookbackTests(unittest.TestCase):
    def test_lookback_parses_and_rejects_grafana_relative_syntax(self) -> None:
        self.assertEqual(verify_live.parse_lookback("30d"), 30 * 86400)
        with self.assertRaises(SystemExit):
            verify_live.parse_lookback("now-30d")


class ReferenceCollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.config = support.config(root=self.root)
        support.write_json(self.root / "dashboards" / "overview.json", {
            "uid": "acme-overview",
            "templating": {"list": [{
                "type": "query", "name": "service", "datasource": "acme-prom",
                "query": 'label_values(target_info{service_namespace="acme"}, service_name)',
            }]},
            "panels": [
                {"title": "Rate", "datasource": "acme-prom", "targets": [
                    {"expr": 'sum by (service_name) (rate(http_requests_total{service_name="acme-web"}[5m]))'},
                    {"expr": 'sum(rate(http_requests_total{service_name=~"$service"}[5m]))'},
                ]},
                {"title": "Logs", "datasource": "acme-logs", "targets": [
                    {"expr": '{service_namespace="acme"} |= "error"'},
                ]},
                {"title": "Journeys", "datasource": "acme-traces", "targets": [
                    {"query": '{ resource.service.namespace = "acme" } | rate()'},
                ]},
            ],
        })
        (self.root / "alerts").mkdir()
        (self.root / "alerts" / "a.yaml").write_text(
            "apiVersion: 1\ngroups:\n  - name: g\n    rules:\n      - uid: acme-a\n        data:\n"
            "          - refId: A\n            datasourceUid: ${PROMETHEUS_DS_UID}\n"
            "            model: { expr: 'sum(rate(errors_total{service_namespace=\"acme\"}[5m]))' }\n"
            "          - refId: L\n            datasourceUid: ${LOKI_DS_UID}\n"
            "            model: { expr: 'count_over_time({service_namespace=\"acme\"}[5m])' }\n"
        )

    def test_collects_metric_names_and_literal_service_values(self) -> None:
        metrics, services = verify_live.collect_references(self.config)
        self.assertEqual(set(metrics), {"http_requests_total", "target_info", "errors_total"})
        self.assertEqual(set(services), {"acme-web"})

    def test_collects_traceql_targets(self) -> None:
        queries = verify_live.collect_traceql(self.config)
        self.assertEqual(len(queries), 1)
        self.assertIn("resource.service.namespace", queries[0][1])

    def test_repo_rule_uids(self) -> None:
        self.assertEqual(verify_live.repo_rule_uids(self.config), {"acme-a"})


class NearMatchTests(unittest.TestCase):
    def test_suggests_a_value_that_differs_only_in_case_and_separators(self) -> None:
        self.assertEqual(verify_live.near_matches("Acme.Web", {"acme-web", "acme-api"}), ["acme-web"])


if __name__ == "__main__":
    unittest.main()
