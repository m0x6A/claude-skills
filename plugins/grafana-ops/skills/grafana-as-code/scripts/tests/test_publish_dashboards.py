#!/usr/bin/env python3
"""Unit tests for the pure parts of publish_dashboards.py (no network).

    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import contextlib
import io
import json
import unittest

import support

import publish_dashboards


class RewriteDatasourcesTests(unittest.TestCase):
    def test_names_become_type_uid_refs_everywhere_and_unknown_names_are_left_alone(self) -> None:
        dashboard = {
            "id": 42,
            "panels": [
                {"datasource": "acme-prom", "targets": [{"datasource": "acme-logs"}]},
                {"type": "row", "panels": [{"datasource": "acme-prom"}]},
                {"datasource": "-- Grafana --"},
            ],
            "templating": {"list": [{"datasource": "acme-prom"}]},
        }
        refs = {"acme-prom": {"type": "prometheus", "uid": "p1"}, "acme-logs": {"type": "loki", "uid": "l1"}}
        prepared = publish_dashboards.prepare_dashboard(dashboard, refs)
        self.assertIsNone(prepared["id"])
        self.assertEqual(prepared["panels"][0]["datasource"], {"type": "prometheus", "uid": "p1"})
        self.assertEqual(prepared["panels"][0]["targets"][0]["datasource"], {"type": "loki", "uid": "l1"})
        self.assertEqual(prepared["panels"][1]["panels"][0]["datasource"], {"type": "prometheus", "uid": "p1"})
        self.assertEqual(prepared["panels"][2]["datasource"], "-- Grafana --")
        self.assertEqual(prepared["templating"]["list"][0]["datasource"]["uid"], "p1")

    def test_each_rewritten_ref_is_its_own_object(self) -> None:
        dashboard = {"panels": [{"datasource": "acme-prom"}, {"datasource": "acme-prom"}]}
        publish_dashboards.rewrite_datasources(dashboard, {"acme-prom": {"type": "prometheus", "uid": "p1"}})
        self.assertIsNot(dashboard["panels"][0]["datasource"], dashboard["panels"][1]["datasource"])


class PruneTests(unittest.TestCase):
    def test_only_prefixed_dashboards_that_left_the_repo_are_pruned(self) -> None:
        existing = [{"uid": "acme-old"}, {"uid": "acme-kept"}, {"uid": "neighbour-overview"}, {"title": "no uid"}]
        self.assertEqual(publish_dashboards.dashboards_to_prune(existing, {"acme-kept"}, "acme-"), ["acme-old"])


class DryRunTests(unittest.TestCase):
    def test_dry_run_against_the_templates_needs_no_network(self) -> None:
        root = support.project_from_templates()
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            publish_dashboards.main(["--config", str(root / "grafana-as-code.json"), "--dry-run", "example-dashboard"])
        header, _, body = out.getvalue().partition("\n")
        self.assertEqual(header, "--- example-dashboard.json :: acme-service-overview")
        payload = json.loads(body)
        self.assertTrue(payload["overwrite"])
        self.assertEqual(payload["dashboard"]["panels"][0]["datasource"]["type"], "prometheus")

    def test_unknown_dashboard_name_exits(self) -> None:
        root = support.project_from_templates()
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            publish_dashboards.main(["--config", str(root / "grafana-as-code.json"), "--dry-run", "nope"])


if __name__ == "__main__":
    unittest.main()
