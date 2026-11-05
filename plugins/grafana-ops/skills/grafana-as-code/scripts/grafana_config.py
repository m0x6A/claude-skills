#!/usr/bin/env python3
"""Loads `grafana-as-code.json`, the one file that tells the linter, the publishers and
the live verifier what "this app" means on a Grafana stack.

Everything project-specific lives here and nowhere else: which directories hold the
dashboards and alert rules, which folder they publish to, the uid prefixes that mark an
object as ours (and therefore safe to prune), the label matcher that scopes a query to
this app on a shared stack, the datasource names, the contact point every rule routes to.

Where it is found, first match wins:

  1. `--config PATH` on the command line;
  2. the `GRAFANA_AS_CODE_CONFIG` environment variable;
  3. the nearest `grafana-as-code.json` walking up from the working directory.

Paths inside the file are relative to the file itself, so the scripts behave the same
whatever directory CI happens to run them from.

Only `dashboards_dir` and `alerts_dir` are required. Every other key switches a check or
a behaviour on; leaving it out switches it off, and each script says so in a one-line
notice instead of silently passing — a check that quietly did nothing is how an
unscoped query reaches production. Unknown keys are an error for the same reason: a typo
like `rule_uid_prefx` would otherwise disable pruning safety without a word. Keys that
start with `_` (`"_comment"`) are ignored, so the file can carry its own documentation.

Credentials are never in this file. They come from the environment: `GRAFANA_URL`,
`GRAFANA_API_TOKEN`, and whatever variable `contact_point.addresses_env` names.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILE_NAME = "grafana-as-code.json"
CONFIG_ENV = "GRAFANA_AS_CODE_CONFIG"

# Grafana plugin type ids. The keys of `datasources` are these, so a resolved name can be
# rewritten to the `{type, uid}` reference the dashboard API prefers.
DATASOURCE_KINDS = ("prometheus", "loki", "tempo")

# Grafana's dashboard grid is always 24 columns wide; the key exists for forks of the
# schema, not because a stack can change it. It is the one optional key with a default.
DEFAULT_GRID_COLUMNS = 24

KNOWN_KEYS = {
    "dashboards_dir",
    "alerts_dir",
    "folder",
    "dashboard_uid_prefix",
    "rule_uid_prefix",
    "scope",
    "datasources",
    "placeholders",
    "contact_point",
    "required_rule_labels",
    "allowed_variables",
    "grid_columns",
}
SCOPE_KEYS = {"label", "value", "service_label", "service_regex", "traceql_attributes"}
CONTACT_POINT_KEYS = {"name", "type", "addresses_env", "settings", "settings_env"}
FOLDER_KEYS = {"title", "uid"}


class ConfigError(Exception):
    """The config file is missing, unreadable, or does not match the schema."""


@dataclass(frozen=True)
class Scope:
    """The matcher that pins a query to this app on a shared stack.

    Either pair is enough on its own: `label`/`value` (a namespace-style label with one
    exact value), or `service_label`/`service_regex` (a per-service label whose values
    must all match the regex). A selector carrying either is scoped.
    """

    label: str | None = None
    value: str | None = None
    service_label: str | None = None
    service_regex: str | None = None
    traceql_attributes: tuple[str, ...] = ()

    def describe(self) -> str:
        """The matcher to suggest in an error message."""
        if self.label and self.value is not None:
            return f'{self.label}="{self.value}"'
        return f'{self.service_label}=~"{self.service_regex}"'


@dataclass(frozen=True)
class ContactPoint:
    name: str
    type: str = "email"
    addresses_env: str | None = None
    settings: dict = field(default_factory=dict)
    settings_env: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Config:
    path: Path
    dashboards_dir: Path
    alerts_dir: Path
    folder_title: str | None = None
    folder_uid: str | None = None
    dashboard_uid_prefix: str | None = None
    rule_uid_prefix: str | None = None
    scope: Scope | None = None
    datasources: dict[str, str] = field(default_factory=dict)
    # Placeholder as written in the YAML (`${PROMETHEUS_DS_UID}`) -> datasource kind.
    placeholders: dict[str, str] = field(default_factory=dict)
    contact_point: ContactPoint | None = None
    required_rule_labels: dict[str, str] = field(default_factory=dict)
    allowed_variables: tuple[str, ...] | None = None
    grid_columns: int = DEFAULT_GRID_COLUMNS

    @property
    def root(self) -> Path:
        return self.path.parent

    def placeholder_for(self, kind: str) -> str | None:
        """The `${...}` placeholder that stands for a datasource kind, if one is configured."""
        for placeholder, placeholder_kind in self.placeholders.items():
            if placeholder_kind == kind:
                return placeholder
        return None

    def notices(self, *features: str) -> list[str]:
        """One line per requested feature that the config leaves switched off."""
        lines = {
            "scope": "scope is not set: queries are not checked for scoping to this app.",
            "traceql": "scope.traceql_attributes is not set: TraceQL queries are not checked for scoping.",
            "folder": "folder is not set: dashboards publish to the General folder.",
            "dashboard_uid_prefix": "dashboard_uid_prefix is not set: dashboard uids are not checked "
            "and --prune is disabled for dashboards.",
            "rule_uid_prefix": "rule_uid_prefix is not set: rule uids are not checked and --prune "
            "is disabled for alert rules.",
            "datasources": "datasources is not set: datasource names are not checked or rewritten "
            "to {type, uid}.",
            "placeholders": "placeholders is not set: alert datasourceUid values are sent as "
            "written, and an alert query counts as Loki only if its datasourceUid mentions loki.",
            "contact_point": "contact_point is not set: rule receivers are not checked and no "
            "contact point is provisioned.",
            "required_rule_labels": "required_rule_labels is not set: rule labels are not checked.",
            "allowed_variables": "allowed_variables is not set: template-variable references are "
            "not checked.",
        }
        off = {
            "scope": self.scope is None,
            "traceql": self.scope is None or not self.scope.traceql_attributes,
            "folder": self.folder_title is None,
            "dashboard_uid_prefix": not self.dashboard_uid_prefix,
            "rule_uid_prefix": not self.rule_uid_prefix,
            "datasources": not self.datasources,
            "placeholders": not self.placeholders,
            "contact_point": self.contact_point is None,
            "required_rule_labels": not self.required_rule_labels,
            "allowed_variables": self.allowed_variables is None,
        }
        # When scope is off entirely, the TraceQL notice would only repeat it.
        if self.scope is None:
            off["traceql"] = False
        return [lines[name] for name in features if off.get(name)]


def print_notices(config: Config, *features: str) -> None:
    for line in config.notices(*features):
        print(f"notice: {line}", file=sys.stderr)


def find_config(explicit: str | os.PathLike | None = None,
                environ: dict | None = None,
                cwd: str | os.PathLike | None = None) -> Path:
    """The config path, by flag, then environment variable, then walking up from cwd."""
    environ = os.environ if environ is None else environ

    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise ConfigError(f"--config {path}: no such file")
        return path.resolve()

    from_env = environ.get(CONFIG_ENV)
    if from_env:
        path = Path(from_env)
        if not path.is_file():
            raise ConfigError(f"{CONFIG_ENV}={from_env}: no such file")
        return path.resolve()

    start = Path(cwd or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        candidate = directory / CONFIG_FILE_NAME
        if candidate.is_file():
            return candidate

    raise ConfigError(
        f"no {CONFIG_FILE_NAME} found in {start} or any parent directory. "
        f"Pass --config PATH or set {CONFIG_ENV}; templates/{CONFIG_FILE_NAME} is a starting point."
    )


def load_config(path: str | os.PathLike) -> Config:
    path = Path(path).resolve()
    try:
        data = json.loads(path.read_text())
    except OSError as error:
        raise ConfigError(f"{path}: {error}") from error
    except json.JSONDecodeError as error:
        raise ConfigError(f"{path} is not valid JSON: {error}") from error
    return config_from_dict(data, path)


def load(explicit: str | os.PathLike | None = None) -> Config:
    """find_config + load_config, exiting with the reason on any config error."""
    try:
        return load_config(find_config(explicit))
    except ConfigError as error:
        sys.exit(f"config error: {error}")


def _check_keys(where: str, data: dict, known: set[str]) -> None:
    unknown = sorted(key for key in data if key not in known and not key.startswith("_"))
    if unknown:
        raise ConfigError(f"{where}: unknown key(s) {unknown}; known keys are {sorted(known)}")


def _string(where: str, value, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ConfigError(f"{where} must be a non-empty string, not {value!r}")
    return value


def _string_map(where: str, value) -> dict[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        raise ConfigError(f"{where} must be an object of string -> string")
    return {k: v for k, v in value.items() if not k.startswith("_")}


def _placeholder(name: str) -> str:
    """`PROMETHEUS_DS_UID` and `${PROMETHEUS_DS_UID}` both mean `${PROMETHEUS_DS_UID}`."""
    bare = name.removeprefix("${").removesuffix("}")
    return "${" + bare + "}"


def config_from_dict(data: dict, path: str | os.PathLike) -> Config:
    path = Path(path)
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: the top level must be a JSON object")
    _check_keys(str(path.name), data, KNOWN_KEYS)

    for key in ("dashboards_dir", "alerts_dir"):
        if key not in data:
            raise ConfigError(f"{path.name}: {key} is required")
    base = path.parent
    dashboards_dir = (base / _string("dashboards_dir", data["dashboards_dir"])).resolve()
    alerts_dir = (base / _string("alerts_dir", data["alerts_dir"])).resolve()

    folder_title = folder_uid = None
    if "folder" in data:
        folder = data["folder"]
        if not isinstance(folder, dict):
            raise ConfigError("folder must be an object with title and uid")
        _check_keys("folder", folder, FOLDER_KEYS)
        folder_title = _string("folder.title", folder.get("title"))
        folder_uid = _string("folder.uid", folder.get("uid"))

    prefixes = {}
    for key in ("dashboard_uid_prefix", "rule_uid_prefix"):
        if key in data:
            prefixes[key] = _string(key, data[key])

    scope = None
    if "scope" in data:
        raw = data["scope"]
        if not isinstance(raw, dict):
            raise ConfigError("scope must be an object")
        _check_keys("scope", raw, SCOPE_KEYS)
        has_namespace = "label" in raw or "value" in raw
        has_service = "service_label" in raw or "service_regex" in raw
        if has_namespace and not ("label" in raw and "value" in raw):
            raise ConfigError("scope.label and scope.value go together")
        if has_service and not ("service_label" in raw and "service_regex" in raw):
            raise ConfigError("scope.service_label and scope.service_regex go together")
        if not (has_namespace or has_service):
            raise ConfigError("scope needs label/value, service_label/service_regex, or both")
        if "service_regex" in raw:
            try:
                re.compile(raw["service_regex"])
            except (re.error, TypeError) as error:
                raise ConfigError(f"scope.service_regex is not a valid regex: {error}") from error
        attributes = raw.get("traceql_attributes", [])
        if not isinstance(attributes, list) or not all(isinstance(a, str) and a for a in attributes):
            raise ConfigError("scope.traceql_attributes must be a list of attribute names")
        scope = Scope(
            label=_string("scope.label", raw["label"]) if "label" in raw else None,
            value=_string("scope.value", raw["value"]) if "value" in raw else None,
            service_label=_string("scope.service_label", raw["service_label"]) if has_service else None,
            service_regex=_string("scope.service_regex", raw["service_regex"]) if has_service else None,
            traceql_attributes=tuple(attributes),
        )

    datasources = {}
    if "datasources" in data:
        datasources = _string_map("datasources", data["datasources"])
        unknown = sorted(set(datasources) - set(DATASOURCE_KINDS))
        if unknown:
            raise ConfigError(f"datasources: unknown kind(s) {unknown}; use {list(DATASOURCE_KINDS)}")

    placeholders = {}
    if "placeholders" in data:
        for name, kind in _string_map("placeholders", data["placeholders"]).items():
            if kind not in DATASOURCE_KINDS:
                raise ConfigError(f"placeholders.{name}: '{kind}' is not one of {list(DATASOURCE_KINDS)}")
            placeholders[_placeholder(name)] = kind

    contact_point = None
    if "contact_point" in data:
        raw = data["contact_point"]
        if not isinstance(raw, dict):
            raise ConfigError("contact_point must be an object")
        _check_keys("contact_point", raw, CONTACT_POINT_KEYS)
        kind = _string("contact_point.type", raw.get("type", "email"))
        addresses_env = raw.get("addresses_env")
        if addresses_env is not None:
            _string("contact_point.addresses_env", addresses_env)
        elif kind == "email":
            raise ConfigError("contact_point.addresses_env is required for an email contact point")
        settings = raw.get("settings", {})
        if not isinstance(settings, dict):
            raise ConfigError("contact_point.settings must be an object")
        contact_point = ContactPoint(
            name=_string("contact_point.name", raw.get("name")),
            type=kind,
            addresses_env=addresses_env,
            settings=settings,
            settings_env=_string_map("contact_point.settings_env", raw.get("settings_env", {})),
        )

    required_rule_labels = {}
    if "required_rule_labels" in data:
        required_rule_labels = _string_map("required_rule_labels", data["required_rule_labels"])

    allowed_variables = None
    if "allowed_variables" in data:
        raw = data["allowed_variables"]
        if not isinstance(raw, list) or not all(isinstance(v, str) and v for v in raw):
            raise ConfigError("allowed_variables must be a list of variable names (without $)")
        allowed_variables = tuple(v.lstrip("$") for v in raw)

    grid_columns = data.get("grid_columns", DEFAULT_GRID_COLUMNS)
    if not isinstance(grid_columns, int) or isinstance(grid_columns, bool) or grid_columns <= 0:
        raise ConfigError("grid_columns must be a positive integer")

    return Config(
        path=path,
        dashboards_dir=dashboards_dir,
        alerts_dir=alerts_dir,
        folder_title=folder_title,
        folder_uid=folder_uid,
        dashboard_uid_prefix=prefixes.get("dashboard_uid_prefix"),
        rule_uid_prefix=prefixes.get("rule_uid_prefix"),
        scope=scope,
        datasources=datasources,
        placeholders=placeholders,
        contact_point=contact_point,
        required_rule_labels=required_rule_labels,
        allowed_variables=allowed_variables,
        grid_columns=grid_columns,
    )
