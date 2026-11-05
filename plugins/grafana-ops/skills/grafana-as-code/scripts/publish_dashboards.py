#!/usr/bin/env python3
"""Publish the dashboards in `dashboards_dir` to Grafana via the HTTP API.

The workflow: validate JSON -> find (or create) the folder -> resolve the configured
datasource names to `{type, uid}` refs -> POST /api/dashboards/db with overwrite ->
verify each push with a GET round-trip -> optionally prune dashboards that left the
repository.

The JSON files reference datasources by NAME (`datasources` in grafana-as-code.json).
Names are the same on every stack that follows a naming convention, and survive a
datasource being recreated; uids do neither. The API prefers `{type, uid}` refs, so the
names are rewritten at push time and the repository never holds a uid.

`overwrite: true` makes the repository the single source of truth: anything edited in
the UI is replaced on the next publish. `--prune` is what makes deletion work too — a
dashboard removed from the repo is deleted live instead of lingering as an orphan the
next reviewer has to explain. It only ever deletes dashboards inside the configured
folder whose uid starts with `dashboard_uid_prefix`, so it cannot reach another app's
dashboards on a shared stack; without both keys it refuses to prune.

Stdlib only (no jq/curl needed).

    export GRAFANA_URL="https://<stack>.grafana.net"
    export GRAFANA_API_TOKEN="<service-account token: dashboards:write, folders:read, folders:write, datasources:read>"
    python3 scripts/publish_dashboards.py                     # push every dashboard
    python3 scripts/publish_dashboards.py overview checkout   # push only the named files
    python3 scripts/publish_dashboards.py --prune             # also delete prefixed dashboards no file defines
    python3 scripts/publish_dashboards.py --dry-run           # print the payloads, no network
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import grafana_config  # noqa: E402

MESSAGE = "publish via publish_dashboards.py"


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


def rewrite_datasources(node, refs_by_name: dict[str, dict]) -> None:
    """Replace name-string datasource refs with {type, uid} objects, recursively."""
    if isinstance(node, dict):
        ds = node.get("datasource")
        if isinstance(ds, str) and ds in refs_by_name:
            node["datasource"] = dict(refs_by_name[ds])
        for value in node.values():
            rewrite_datasources(value, refs_by_name)
    elif isinstance(node, list):
        for item in node:
            rewrite_datasources(item, refs_by_name)


def prepare_dashboard(dashboard: dict, refs_by_name: dict[str, dict]) -> dict:
    rewrite_datasources(dashboard, refs_by_name)
    dashboard["id"] = None  # id is instance-local; uid is the identity
    return dashboard


def dashboards_to_prune(existing: list[dict], repo_uids: set[str], prefix: str) -> list[str]:
    """Our dashboards (by uid prefix) that no file defines any more; never another app's."""
    return sorted(
        item["uid"]
        for item in existing
        if str(item.get("uid", "")).startswith(prefix)
        and item["uid"] not in repo_uids
    )


def dashboard_files(directory: Path, names: list[str]) -> list[Path]:
    if names:
        files = [directory / f"{n.removesuffix('.json')}.json" for n in names]
        missing = [str(f) for f in files if not f.is_file()]
        if missing:
            sys.exit(f"ERROR: no such dashboard file(s): {', '.join(missing)}")
        return files
    return sorted(directory.glob("*.json"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*", help="dashboard files to push, with or without .json (default: all)")
    parser.add_argument("--config", help="path to grafana-as-code.json")
    parser.add_argument("--prune", action="store_true",
                        help="delete dashboards in the folder with the uid prefix that no file defines any more")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the payloads that would be sent; no network access")
    args = parser.parse_args(argv)

    config = grafana_config.load(args.config)
    grafana_config.print_notices(config, "folder", "datasources")

    if not config.dashboards_dir.is_dir():
        sys.exit(f"ERROR: dashboards_dir {config.dashboards_dir} does not exist")
    files = dashboard_files(config.dashboards_dir, args.names)

    can_prune = bool(config.dashboard_uid_prefix and config.folder_title)
    if args.prune and args.names:
        print("notice: --prune is ignored when publishing named dashboards.", file=sys.stderr)
    elif args.prune and not can_prune:
        print("notice: --prune needs both folder and dashboard_uid_prefix in the config; skipping prune.",
              file=sys.stderr)

    if args.dry_run:
        refs = {name: {"type": kind, "uid": f"<uid of {name}>"} for kind, name in config.datasources.items()}
        for f in files:
            dashboard = prepare_dashboard(json.loads(f.read_text()), refs)
            print(f"--- {f.name} :: {dashboard.get('uid')}")
            print(json.dumps({
                "dashboard": dashboard,
                "folderUid": f"<uid of {config.folder_title}>" if config.folder_title else "",
                "overwrite": True,
                "message": MESSAGE,
            }, indent=2))
        return

    base = os.environ.get("GRAFANA_URL") or sys.exit("Set GRAFANA_URL, e.g. https://<stack>.grafana.net")
    token = os.environ.get("GRAFANA_API_TOKEN") or sys.exit("Set GRAFANA_API_TOKEN (service-account token)")
    base = base.rstrip("/")

    # 1. Find the dashboards folder (creating it only if it does not exist yet).
    folder_uid = ""
    if config.folder_title:
        folder_uid = resolve_folder(base, token, config.folder_title, config.folder_uid)
        print(f"folder:     {config.folder_title} -> uid={folder_uid}")

    # 2. Resolve datasource names -> {type, uid}.
    refs_by_name: dict[str, dict] = {}
    for kind, name in config.datasources.items():
        ds = api(base, token, f"/api/datasources/name/{urllib.parse.quote(name, safe='')}")
        if ds is None:
            sys.exit(f"ERROR: datasource '{name}' not found on {base}")
        refs_by_name[name] = {"type": kind, "uid": ds["uid"]}
        print(f"datasource: {name} -> uid={ds['uid']}")

    # 3. Push each dashboard, then verify with a GET round-trip.
    pushed: set[str] = set()
    for f in files:
        dashboard = prepare_dashboard(json.loads(f.read_text()), refs_by_name)  # validates JSON

        resp = api(base, token, "/api/dashboards/db", {
            "dashboard": dashboard,
            "folderUid": folder_uid,
            "overwrite": True,
            "message": MESSAGE,
        })
        print(f"pushed:   {f.name} -> {resp['status']} v{resp['version']} {resp['url']}")

        check = api(base, token, f"/api/dashboards/uid/{resp['uid']}")
        if check is None:
            sys.exit(f"ERROR: {f.name} was accepted but GET /api/dashboards/uid/{resp['uid']} returns 404")
        pushed.add(resp["uid"])
        print(f"verified: {check['dashboard']['title']} ({len(check['dashboard'].get('panels', []))} panels)")

    # 4. Prune dashboards that left the repository (only ours, only in our folder).
    if args.prune and not args.names and can_prune:
        query = urllib.parse.urlencode({"type": "dash-db", "folderUIDs": folder_uid, "limit": 5000})
        existing = api(base, token, f"/api/search?{query}") or []
        for uid in dashboards_to_prune(existing, pushed, config.dashboard_uid_prefix):
            api(base, token, f"/api/dashboards/uid/{uid}", method="DELETE")
            print(f"pruned:   {uid}")

    print(f"\nDone. Open {base}/dashboards -> {config.folder_title or 'General'} and confirm panels render with data.")


if __name__ == "__main__":
    main()
