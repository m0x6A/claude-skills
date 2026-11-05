"""Shared helpers for the unit tests: puts scripts/ on sys.path and builds configs.

    python3 -m unittest discover -s scripts/tests
"""

from __future__ import annotations

import copy
import json
import pathlib
import shutil
import sys
import tempfile

SCRIPTS = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = SCRIPTS.parent / "templates"
sys.path.insert(0, str(SCRIPTS))

import grafana_config  # noqa: E402

FULL = {
    "dashboards_dir": "dashboards",
    "alerts_dir": "alerts",
    "folder": {"title": "Acme Shop", "uid": "acme-shop"},
    "dashboard_uid_prefix": "acme-",
    "rule_uid_prefix": "acme-",
    "scope": {
        "label": "service_namespace",
        "value": "acme",
        "service_label": "service_name",
        "service_regex": "acme-.*",
        "traceql_attributes": ["resource.service.namespace", "resource.service.name"],
    },
    "datasources": {"prometheus": "acme-prom", "loki": "acme-logs", "tempo": "acme-traces"},
    "placeholders": {"PROMETHEUS_DS_UID": "prometheus", "LOKI_DS_UID": "loki"},
    "contact_point": {"name": "acme-email", "type": "email", "addresses_env": "ALERT_EMAIL"},
    "required_rule_labels": {"app": "acme"},
    "allowed_variables": ["service", "__range", "__interval", "__rate_interval"],
}


def config(overrides: dict | None = None, drop: tuple[str, ...] = (), root: pathlib.Path | None = None):
    """A Config from FULL with `overrides` merged in and `drop` keys removed."""
    data = copy.deepcopy(FULL)
    data.update(overrides or {})
    for key in drop:
        data.pop(key, None)
    path = (root or pathlib.Path("/nonexistent")) / grafana_config.CONFIG_FILE_NAME
    return grafana_config.config_from_dict(data, path)


def project_from_templates() -> pathlib.Path:
    """A temp project laid out the way templates/grafana-as-code.json expects."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="grafana-as-code-"))
    dashboards = root / "telemetry" / "grafana" / "dashboards"
    alerts = root / "telemetry" / "grafana" / "alerts"
    dashboards.mkdir(parents=True)
    alerts.mkdir(parents=True)
    shutil.copy(TEMPLATES / "grafana-as-code.json", root / grafana_config.CONFIG_FILE_NAME)
    shutil.copy(TEMPLATES / "example-dashboard.json", dashboards / "example-dashboard.json")
    shutil.copy(TEMPLATES / "example-alert.yaml", alerts / "example-alert.yaml")
    return root


def write_json(path: pathlib.Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
