#!/usr/bin/env python3
"""Publish the alert rules in `alerts_dir` and their contact point to Grafana.

Mirrors publish_dashboards.py for alert rules written in Grafana's file-provisioning
format (`apiVersion: 1`, `groups:` of `rules:`): resolve the datasource uids (replacing
placeholders such as `${PROMETHEUS_DS_UID}` via `placeholders` -> `datasources` in
grafana-as-code.json) -> find (or create) the folder -> provision the contact point ->
upsert each rule via /api/v1/provisioning/alert-rules (POST new, PUT existing) -> set the
group evaluation interval -> verify each rule with a GET round-trip -> optionally prune
rules that left the repository.

The YAML never names a datasource uid: uids differ per stack and change when a
datasource is recreated. The placeholder names the kind of datasource; the config names
the datasource; the uid is looked up at publish time.

Routing is per rule, and that is a deliberate choice. Every rule carries
`notification_settings.receiver: <contact_point.name>`, which Grafana turns into an
auto-generated route for that rule alone. This script never reads or writes the
notification-policy tree. That tree is one global object per stack: on a stack shared
with other apps or teams, replacing it to add "our" route would silently drop theirs,
and merging into it means owning a structure other people also edit. A receiver on the
rule keeps this app's routing entirely inside this app's rules. (The trade-off: grouping,
timing and mute settings come from `notification_settings` on each rule, not from a
policy subtree.)

Rules and the contact point are pushed with provenance "api": they cannot be edited in
the Grafana UI, which keeps the repository the single source of truth. `--prune` deletes
only rules in the configured folder whose uid starts with `rule_uid_prefix`.

Requires PyYAML (the one non-stdlib dependency): python3 -m pip install pyyaml

    export GRAFANA_URL="https://<stack>.grafana.net"
    export GRAFANA_API_TOKEN="<service-account token: alert rules write, contact points write, folders:read, folders:write, datasources:read>"
    export <contact_point.addresses_env>="<where the alerts go>"
    python3 scripts/publish_alerts.py                       # push every alert file
    python3 scripts/publish_alerts.py service-health auth   # push only the named files
    python3 scripts/publish_alerts.py --prune               # also delete prefixed rules no file defines
    python3 scripts/publish_alerts.py --dry-run --skip-contact-point   # print the payloads, no network
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import grafana_config  # noqa: E402

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: python3 -m pip install pyyaml")

EXPRESSION_DATASOURCE = "__expr__"


def api(base: str, token: str, path: str, payload: dict | None = None,
        method: str | None = None) -> dict | list | None:
    """The decoded response; None on 404; exits with the body on any other error."""
    method = method or ("POST" if payload is not None else "GET")
    req = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        body = e.read().decode(errors="replace")[:500]
        sys.exit(f"ERROR {e.code} on {method} {path}: {body}")


def resolve_folder(base: str, token: str, title: str, uid: str) -> str:
    """UID of the folder titled `title`, created (with `uid`) only if it does not exist.

    Matched by title, not by uid: the folder may already exist with a Grafana-assigned uid
    (made in the UI, or by an earlier tool), and some stacks answer GET /api/folders/<unknown
    uid> with 403 rather than 404 — so probing by uid cannot tell "missing" from "forbidden".
    """
    for folder in api(base, token, "/api/folders?limit=1000") or []:
        if folder["title"].casefold() == title.casefold():
            return folder["uid"]
    created = api(base, token, "/api/folders", {"uid": uid, "title": title})
    print(f"folder created: {created['title']} (uid={created['uid']})")
    return created["uid"]


def interval_seconds(value: str | int) -> int:
    """Parse a Grafana duration like '1m' / '30s' / '1h' into seconds."""
    if isinstance(value, int):
        return value
    match = re.fullmatch(r"(\d+)([smh])", value.strip())
    if not match:
        sys.exit(f"ERROR: cannot parse group interval '{value}'")
    return int(match.group(1)) * {"s": 1, "m": 60, "h": 3600}[match.group(2)]


def prepare_rule(rule: dict, group: dict, folder_uid: str, uid_by_placeholder: dict[str, str] | None) -> dict:
    """The provisioning payload for one rule: placeholders resolved, folder and group set.

    `uid_by_placeholder` None means no placeholders are configured: datasourceUid values
    are literal uids and are sent as written.
    """
    for query in rule.get("data", []):
        datasource = query.get("datasourceUid")
        if datasource == EXPRESSION_DATASOURCE or uid_by_placeholder is None:
            continue
        if datasource not in uid_by_placeholder:
            sys.exit(
                f"ERROR: rule {rule.get('uid')} query {query.get('refId')} uses datasource "
                f"'{datasource}'; known placeholders are {sorted(uid_by_placeholder)}"
            )
        query["datasourceUid"] = uid_by_placeholder[datasource]

    rule["folderUID"] = folder_uid
    rule["ruleGroup"] = group["name"]
    rule.setdefault("orgID", group.get("orgId", 1))
    return rule


def contact_point_payload(contact_point: grafana_config.ContactPoint, environ: dict | None = None,
                          placeholder_missing: bool = False) -> dict:
    """The provisioning payload for the configured contact point.

    Secrets (addresses, webhook URLs) come from the environment variables the config
    names; with `placeholder_missing` an unset variable is shown as `<NAME>` (dry run).
    An email contact point is delivered by Grafana's own mailer (on Grafana Cloud, no SMTP
    to configure) as a single message to all addresses.
    """
    environ = os.environ if environ is None else environ

    def from_env(name: str) -> str:
        value = environ.get(name)
        if value:
            return value
        if placeholder_missing:
            return f"<{name}>"
        sys.exit(f"Set {name} (used by contact point {contact_point.name}), "
                 "or pass --skip-contact-point for a local run.")

    settings: dict = {"singleEmail": True} if contact_point.type == "email" else {}
    settings.update(contact_point.settings)
    if contact_point.addresses_env:
        settings["addresses"] = from_env(contact_point.addresses_env)
    for key, env_name in contact_point.settings_env.items():
        settings[key] = from_env(env_name)

    return {
        "name": contact_point.name,
        "type": contact_point.type,
        "settings": settings,
        "disableResolveMessage": False,
    }


def rules_to_prune(existing: list[dict], repo_uids: set[str], folder_uid: str, prefix: str) -> list[str]:
    """Our rules in our folder that no file defines any more; never another app's."""
    return sorted(
        rule["uid"]
        for rule in existing
        if rule.get("folderUID") == folder_uid
        and str(rule.get("uid", "")).startswith(prefix)
        and rule["uid"] not in repo_uids
    )


def ensure_contact_point(base: str, token: str, payload: dict) -> None:
    name = payload["name"]
    query = urllib.parse.urlencode({"name": name})
    existing = api(base, token, f"/api/v1/provisioning/contact-points?{query}") or []
    if existing:
        uid = existing[0]["uid"]
        api(base, token, f"/api/v1/provisioning/contact-points/{uid}", payload, method="PUT")
        print(f"contact point: {name} updated (uid={uid})")
    else:
        created = api(base, token, "/api/v1/provisioning/contact-points", payload)
        print(f"contact point: {name} created (uid={(created or {}).get('uid', '?')})")


def alert_files(directory: Path, names: list[str]) -> list[Path]:
    if names:
        files = []
        for n in names:
            stem = n.removesuffix(".yaml").removesuffix(".yml")
            candidates = [directory / f"{stem}.yaml", directory / f"{stem}.yml"]
            found = next((c for c in candidates if c.is_file()), None)
            if found is None:
                sys.exit(f"ERROR: no such alert file: {candidates[0]}")
            files.append(found)
        return files
    return sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))


def load_groups(path: Path) -> list[dict]:
    return (yaml.safe_load(path.read_text()) or {}).get("groups", []) or []


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*", help="alert files to push, with or without .yaml (default: all)")
    parser.add_argument("--config", help="path to grafana-as-code.json")
    parser.add_argument("--prune", action="store_true",
                        help="delete rules in the folder with the uid prefix that no file defines any more")
    parser.add_argument("--skip-contact-point", action="store_true",
                        help="do not provision the contact point (local runs without its secret)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the payloads that would be sent; no network access")
    args = parser.parse_args(argv)

    config = grafana_config.load(args.config)
    grafana_config.print_notices(config, "placeholders", "contact_point")

    if config.folder_title is None:
        sys.exit("config error: folder is required to publish alert rules — the provisioning API "
                 "puts every rule in a folder.")
    if not config.alerts_dir.is_dir():
        sys.exit(f"ERROR: alerts_dir {config.alerts_dir} does not exist")
    files = alert_files(config.alerts_dir, args.names)

    if args.prune and args.names:
        print("notice: --prune is ignored when publishing named files.", file=sys.stderr)
    elif args.prune and not config.rule_uid_prefix:
        print("notice: --prune needs rule_uid_prefix in the config; skipping prune.", file=sys.stderr)

    contact_point = None if args.skip_contact_point else config.contact_point

    if args.dry_run:
        uid_by_placeholder = (
            {placeholder: f"<uid of {config.datasources.get(kind, kind)}>"
             for placeholder, kind in config.placeholders.items()}
            if config.placeholders else None
        )
        for f in files:
            for group in load_groups(f):
                for rule in group.get("rules", []) or []:
                    prepared = prepare_rule(rule, group, f"<uid of {config.folder_title}>", uid_by_placeholder)
                    print(f"--- {f.name} :: {prepared.get('uid')}")
                    print(json.dumps(prepared, indent=2))
        if contact_point is not None:
            print("--- contact point")
            print(json.dumps(contact_point_payload(contact_point, placeholder_missing=True), indent=2))
        return

    base = os.environ.get("GRAFANA_URL") or sys.exit("Set GRAFANA_URL, e.g. https://<stack>.grafana.net")
    token = os.environ.get("GRAFANA_API_TOKEN") or sys.exit("Set GRAFANA_API_TOKEN (service-account token)")
    base = base.rstrip("/")

    # Read the secret before touching the stack, so a missing one changes nothing.
    contact_payload = contact_point_payload(contact_point) if contact_point is not None else None

    # 1. Resolve the datasource uids for the placeholders.
    uid_by_placeholder: dict[str, str] | None = None
    if config.placeholders:
        uid_by_placeholder = {}
        for placeholder, kind in config.placeholders.items():
            name = config.datasources.get(kind)
            if name is None:
                sys.exit(f"config error: placeholder {placeholder} means '{kind}', but datasources.{kind} is not set")
            ds = api(base, token, f"/api/datasources/name/{urllib.parse.quote(name, safe='')}")
            if ds is None:
                sys.exit(f"ERROR: datasource '{name}' not found on {base}")
            uid_by_placeholder[placeholder] = ds["uid"]
            print(f"datasource: {name} -> uid={ds['uid']}")

    # 2. Find the alerts folder (creating it only if it does not exist yet).
    folder_uid = resolve_folder(base, token, config.folder_title, config.folder_uid)
    print(f"folder:     {config.folder_title} -> uid={folder_uid}")

    # 3. The contact point every rule routes to.
    if contact_payload is not None:
        ensure_contact_point(base, token, contact_payload)

    # 4. Upsert every rule in every group, then set the group interval.
    pushed: set[str] = set()
    for f in files:
        for group in load_groups(f):
            for rule in group.get("rules", []) or []:
                prepare_rule(rule, group, folder_uid, uid_by_placeholder)

                uid = rule["uid"]
                exists = api(base, token, f"/api/v1/provisioning/alert-rules/{uid}") is not None
                if exists:
                    api(base, token, f"/api/v1/provisioning/alert-rules/{uid}", rule, method="PUT")
                else:
                    api(base, token, "/api/v1/provisioning/alert-rules", rule)
                pushed.add(uid)
                print(f"pushed:   {f.name} :: {uid} ({'updated' if exists else 'created'})")

                check = api(base, token, f"/api/v1/provisioning/alert-rules/{uid}")
                if check is None:
                    sys.exit(f"ERROR: rule {uid} was accepted but GET returns 404")
                print(f"verified: {check['title']} "
                      f"[{(check.get('labels') or {}).get('severity', '?')}] -> "
                      f"{(check.get('notification_settings') or {}).get('receiver', 'no receiver')}")

            api(base, token,
                f"/api/v1/provisioning/folder/{folder_uid}/rule-groups/{urllib.parse.quote(group['name'], safe='')}",
                {"interval": interval_seconds(group.get("interval", "1m"))},
                method="PUT")
            print(f"interval: {group['name']} -> {group.get('interval', '1m')}")

    # 5. Prune rules that left the repository (only ours, only in our folder).
    if args.prune and not args.names and config.rule_uid_prefix:
        existing = api(base, token, "/api/v1/provisioning/alert-rules") or []
        for uid in rules_to_prune(existing, pushed, folder_uid, config.rule_uid_prefix):
            api(base, token, f"/api/v1/provisioning/alert-rules/{uid}", method="DELETE")
            print(f"pruned:   {uid}")

    print(f"\nDone. Open {base}/alerting/list -> {config.folder_title} and confirm "
          "the rules are Normal (not NoData/Error).")


if __name__ == "__main__":
    main()
