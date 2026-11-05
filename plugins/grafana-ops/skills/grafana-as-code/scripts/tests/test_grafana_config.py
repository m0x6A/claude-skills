#!/usr/bin/env python3
"""Unit tests for grafana_config.py: discovery, schema validation, notices.

    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

import support
from support import grafana_config


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = pathlib.Path(tempfile.mkdtemp())
        self.config_path = self.root / grafana_config.CONFIG_FILE_NAME
        self.config_path.write_text(json.dumps({"dashboards_dir": "d", "alerts_dir": "a"}))
        self.nested = self.root / "x" / "y"
        self.nested.mkdir(parents=True)

    def test_explicit_path_wins_over_the_environment(self) -> None:
        other = self.root / "other.json"
        other.write_text("{}")
        found = grafana_config.find_config(other, environ={grafana_config.CONFIG_ENV: str(self.config_path)})
        self.assertEqual(found, other.resolve())

    def test_environment_variable_wins_over_walking_up(self) -> None:
        elsewhere = pathlib.Path(tempfile.mkdtemp()) / "custom.json"
        elsewhere.write_text("{}")
        found = grafana_config.find_config(None, environ={grafana_config.CONFIG_ENV: str(elsewhere)}, cwd=self.nested)
        self.assertEqual(found, elsewhere.resolve())

    def test_walks_up_from_the_working_directory(self) -> None:
        self.assertEqual(grafana_config.find_config(None, environ={}, cwd=self.nested), self.config_path.resolve())

    def test_missing_explicit_path_is_an_error(self) -> None:
        with self.assertRaises(grafana_config.ConfigError):
            grafana_config.find_config(self.root / "nope.json", environ={})

    def test_missing_environment_path_is_an_error(self) -> None:
        with self.assertRaises(grafana_config.ConfigError):
            grafana_config.find_config(None, environ={grafana_config.CONFIG_ENV: str(self.root / "nope.json")})

    def test_nothing_found_is_an_error_that_names_the_ways_to_fix_it(self) -> None:
        empty = pathlib.Path(tempfile.mkdtemp())
        with self.assertRaises(grafana_config.ConfigError) as caught:
            grafana_config.find_config(None, environ={}, cwd=empty)
        self.assertIn("--config", str(caught.exception))
        self.assertIn(grafana_config.CONFIG_ENV, str(caught.exception))

    def test_dirs_resolve_relative_to_the_config_file_not_the_cwd(self) -> None:
        config = grafana_config.load_config(self.config_path)
        self.assertEqual(config.dashboards_dir, (self.root / "d").resolve())
        self.assertEqual(config.alerts_dir, (self.root / "a").resolve())

    def test_invalid_json_is_an_error(self) -> None:
        self.config_path.write_text("{ not json")
        with self.assertRaises(grafana_config.ConfigError):
            grafana_config.load_config(self.config_path)


class SchemaTests(unittest.TestCase):
    def assert_rejected(self, data: dict, fragment: str) -> None:
        with self.assertRaises(grafana_config.ConfigError) as caught:
            grafana_config.config_from_dict(data, pathlib.Path("/x/grafana-as-code.json"))
        self.assertIn(fragment, str(caught.exception))

    def minimal(self, **extra) -> dict:
        return {"dashboards_dir": "d", "alerts_dir": "a", **extra}

    def test_dirs_are_required(self) -> None:
        self.assert_rejected({"alerts_dir": "a"}, "dashboards_dir")
        self.assert_rejected({"dashboards_dir": "d"}, "alerts_dir")

    def test_unknown_key_is_an_error_so_a_typo_cannot_disable_a_check(self) -> None:
        self.assert_rejected(self.minimal(rule_uid_prefx="acme-"), "rule_uid_prefx")

    def test_unknown_nested_key_is_an_error(self) -> None:
        self.assert_rejected(self.minimal(scope={"label": "ns", "value": "a", "lable": "x"}), "lable")

    def test_underscore_keys_are_comments(self) -> None:
        config = grafana_config.config_from_dict(
            self.minimal(_comment={"anything": "goes"}, scope={"_comment": "x", "label": "ns", "value": "a"},
                         datasources={"_comment": "x", "prometheus": "p"}),
            pathlib.Path("/x/grafana-as-code.json"),
        )
        self.assertEqual(config.datasources, {"prometheus": "p"})

    def test_scope_pairs_must_be_complete(self) -> None:
        self.assert_rejected(self.minimal(scope={"label": "ns"}), "go together")
        self.assert_rejected(self.minimal(scope={"service_label": "svc"}), "go together")
        self.assert_rejected(self.minimal(scope={"traceql_attributes": ["a"]}), "needs")

    def test_service_regex_must_compile(self) -> None:
        self.assert_rejected(self.minimal(scope={"service_label": "s", "service_regex": "acme-("}), "regex")

    def test_service_scope_alone_is_enough(self) -> None:
        config = grafana_config.config_from_dict(
            self.minimal(scope={"service_label": "service_name", "service_regex": "acme-.*"}),
            pathlib.Path("/x/grafana-as-code.json"),
        )
        self.assertIsNone(config.scope.label)
        self.assertEqual(config.scope.describe(), 'service_name=~"acme-.*"')

    def test_placeholders_are_normalised_to_the_yaml_spelling(self) -> None:
        config = support.config({"placeholders": {"PROMETHEUS_DS_UID": "prometheus", "${LOKI_DS_UID}": "loki"}})
        self.assertEqual(config.placeholders, {"${PROMETHEUS_DS_UID}": "prometheus", "${LOKI_DS_UID}": "loki"})
        self.assertEqual(config.placeholder_for("loki"), "${LOKI_DS_UID}")

    def test_placeholder_kind_must_be_a_datasource_kind(self) -> None:
        self.assert_rejected(self.minimal(placeholders={"X": "mysql"}), "mysql")

    def test_datasource_kind_must_be_known(self) -> None:
        self.assert_rejected(self.minimal(datasources={"graphite": "g"}), "graphite")

    def test_email_contact_point_needs_an_address_variable(self) -> None:
        self.assert_rejected(self.minimal(contact_point={"name": "x", "type": "email"}), "addresses_env")

    def test_webhook_contact_point_takes_secrets_from_the_environment(self) -> None:
        config = grafana_config.config_from_dict(
            self.minimal(contact_point={"name": "hook", "type": "webhook", "settings_env": {"url": "HOOK_URL"}}),
            pathlib.Path("/x/grafana-as-code.json"),
        )
        self.assertEqual(config.contact_point.settings_env, {"url": "HOOK_URL"})

    def test_allowed_variables_drop_a_leading_dollar(self) -> None:
        config = grafana_config.config_from_dict(self.minimal(allowed_variables=["$service", "__range"]),
                                                 pathlib.Path("/x/grafana-as-code.json"))
        self.assertEqual(config.allowed_variables, ("service", "__range"))

    def test_grid_columns_defaults_to_24_and_must_be_positive(self) -> None:
        config = grafana_config.config_from_dict(self.minimal(), pathlib.Path("/x/grafana-as-code.json"))
        self.assertEqual(config.grid_columns, 24)
        self.assert_rejected(self.minimal(grid_columns=0), "grid_columns")


class NoticeTests(unittest.TestCase):
    FEATURES = ("scope", "traceql", "folder", "dashboard_uid_prefix", "rule_uid_prefix", "datasources",
                "placeholders", "contact_point", "required_rule_labels", "allowed_variables")

    def test_minimal_config_reports_every_disabled_check_once(self) -> None:
        config = grafana_config.config_from_dict({"dashboards_dir": "d", "alerts_dir": "a"},
                                                 pathlib.Path("/x/grafana-as-code.json"))
        notices = config.notices(*self.FEATURES)
        # traceql folds into the scope notice when scope is absent altogether.
        self.assertEqual(len(notices), len(self.FEATURES) - 1)
        self.assertTrue(all("\n" not in line for line in notices))

    def test_full_config_reports_nothing(self) -> None:
        self.assertEqual(support.config().notices(*self.FEATURES), [])

    def test_scope_without_traceql_attributes_reports_only_traceql(self) -> None:
        scope = dict(support.FULL["scope"])
        del scope["traceql_attributes"]
        notices = support.config({"scope": scope}).notices("scope", "traceql")
        self.assertEqual(len(notices), 1)
        self.assertIn("TraceQL", notices[0])

    def test_the_shipped_template_is_a_complete_config(self) -> None:
        config = grafana_config.load_config(support.TEMPLATES / "grafana-as-code.json")
        self.assertEqual(config.notices(*self.FEATURES), [])
        self.assertEqual(config.contact_point.name, "acme-email")


if __name__ == "__main__":
    unittest.main()
