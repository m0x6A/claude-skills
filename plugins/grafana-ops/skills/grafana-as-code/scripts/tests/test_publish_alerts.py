#!/usr/bin/env python3
"""Unit tests for the pure parts of publish_alerts.py (no network).

    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import contextlib
import io
import unittest

import support
from support import grafana_config

import publish_alerts


class PrepareRuleTests(unittest.TestCase):
    def test_substitutes_both_datasource_placeholders_and_sets_folder_and_group(self) -> None:
        rule = {
            "uid": "acme-x",
            "data": [
                {"refId": "A", "datasourceUid": "${PROMETHEUS_DS_UID}", "model": {}},
                {"refId": "L", "datasourceUid": "${LOKI_DS_UID}", "model": {}},
                {"refId": "C", "datasourceUid": "__expr__", "model": {}},
            ],
        }
        prepared = publish_alerts.prepare_rule(
            rule, {"name": "service-health", "orgId": 1}, "folder-1",
            {"${PROMETHEUS_DS_UID}": "prom-uid", "${LOKI_DS_UID}": "loki-uid"},
        )
        self.assertEqual([q["datasourceUid"] for q in prepared["data"]], ["prom-uid", "loki-uid", "__expr__"])
        self.assertEqual(prepared["folderUID"], "folder-1")
        self.assertEqual(prepared["ruleGroup"], "service-health")
        self.assertEqual(prepared["orgID"], 1)

    def test_prepare_rule_keeps_isPaused(self) -> None:
        # The provisioning API honours the flag only if the payload carries it.
        rule = {
            "uid": "acme-paused",
            "isPaused": True,
            "data": [{"refId": "A", "datasourceUid": "${PROMETHEUS_DS_UID}", "model": {}}],
        }
        prepared = publish_alerts.prepare_rule(
            rule, {"name": "messaging", "orgId": 1}, "folder-1", {"${PROMETHEUS_DS_UID}": "prom-uid"},
        )
        self.assertIs(prepared["isPaused"], True)

    def test_unknown_placeholder_is_rejected(self) -> None:
        rule = {"uid": "acme-x", "data": [{"refId": "A", "datasourceUid": "${TEMPO_DS_UID}", "model": {}}]}
        with self.assertRaises(SystemExit):
            publish_alerts.prepare_rule(rule, {"name": "g"}, "f", {"${PROMETHEUS_DS_UID}": "p"})

    def test_without_placeholders_datasource_uids_are_sent_as_written(self) -> None:
        rule = {"uid": "acme-x", "data": [{"refId": "A", "datasourceUid": "literal-uid", "model": {}}]}
        prepared = publish_alerts.prepare_rule(rule, {"name": "g"}, "f", None)
        self.assertEqual(prepared["data"][0]["datasourceUid"], "literal-uid")


class IntervalTests(unittest.TestCase):
    def test_durations_parse_to_seconds(self) -> None:
        self.assertEqual(publish_alerts.interval_seconds("1m"), 60)
        self.assertEqual(publish_alerts.interval_seconds("30s"), 30)
        self.assertEqual(publish_alerts.interval_seconds(120), 120)
        with self.assertRaises(SystemExit):
            publish_alerts.interval_seconds("1d")


class ContactPointTests(unittest.TestCase):
    def test_email_contact_point_payload(self) -> None:
        contact_point = support.config().contact_point
        payload = publish_alerts.contact_point_payload(contact_point, {"ALERT_EMAIL": "ops@example.test"})
        self.assertEqual(payload["name"], "acme-email")
        self.assertEqual(payload["type"], "email")
        self.assertEqual(payload["settings"]["addresses"], "ops@example.test")
        self.assertTrue(payload["settings"]["singleEmail"])

    def test_missing_address_variable_exits_naming_it(self) -> None:
        contact_point = support.config().contact_point
        with self.assertRaises(SystemExit) as caught:
            publish_alerts.contact_point_payload(contact_point, {})
        self.assertIn("ALERT_EMAIL", str(caught.exception.code))

    def test_dry_run_shows_the_variable_name_instead_of_a_secret(self) -> None:
        contact_point = support.config().contact_point
        payload = publish_alerts.contact_point_payload(contact_point, {}, placeholder_missing=True)
        self.assertEqual(payload["settings"]["addresses"], "<ALERT_EMAIL>")

    def test_webhook_contact_point_combines_static_and_secret_settings(self) -> None:
        contact_point = grafana_config.ContactPoint(
            name="acme-hook", type="webhook", settings={"httpMethod": "POST"}, settings_env={"url": "HOOK_URL"},
        )
        payload = publish_alerts.contact_point_payload(contact_point, {"HOOK_URL": "https://hooks.example.test/x"})
        self.assertEqual(payload["settings"], {"httpMethod": "POST", "url": "https://hooks.example.test/x"})
        self.assertNotIn("singleEmail", payload["settings"])


class PruneTests(unittest.TestCase):
    def test_only_our_rules_in_the_folder_that_left_the_repo_are_pruned(self) -> None:
        existing = [
            {"uid": "acme-old", "folderUID": "f"},
            {"uid": "acme-kept", "folderUID": "f"},
            {"uid": "acme-elsewhere", "folderUID": "other"},
            {"uid": "neighbour-high-5xx", "folderUID": "f"},
        ]
        self.assertEqual(publish_alerts.rules_to_prune(existing, {"acme-kept"}, "f", "acme-"), ["acme-old"])


class DryRunTests(unittest.TestCase):
    def test_dry_run_against_the_templates_needs_no_network_or_secrets(self) -> None:
        root = support.project_from_templates()
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            publish_alerts.main(["--config", str(root / "grafana-as-code.json"), "--dry-run"])
        text = out.getvalue()
        self.assertIn("--- example-alert.yaml :: acme-http-5xx", text)
        self.assertIn("<uid of grafanacloud-acme-prom>", text)
        self.assertIn("<GRAFANA_ALERT_EMAIL>", text)


if __name__ == "__main__":
    unittest.main()
