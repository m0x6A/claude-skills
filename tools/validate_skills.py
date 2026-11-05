#!/usr/bin/env python3
"""Repository checks that `claude plugin validate` does not make.

    python3 tools/validate_skills.py                 # all checks
    python3 tools/validate_skills.py --base origin/main   # also require version bumps

`claude plugin validate` checks manifests and frontmatter shape. This checks what breaks a skill
in practice: a reference to a template that is not there, a sibling skill or agent that was renamed,
a marketplace entry that drifted from its plugin.json, a plugin changed without a version bump (so
nobody receives the change), a README that forgot a skill, and the feature-workflow diagram palette
drifting between the style guide, the design template and the render page.

Stdlib only. Exit 1 on any error. On GitHub Actions, errors become file annotations.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_DESCRIPTION = 1024
MAX_SKILL_LINES = 500
# Skills and agents that live in other marketplaces and may be named in prose.
EXTERNAL_NAMES = {"skill-creator", "frontend-design"}
DIAGRAM_CLASSES = ("affected", "new", "quiet", "ext", "ok", "err")
RENDER_SLOTS = ("<!--TITLE-->", "<!--ISSUE-->", "<!--DATE-->", "<!--MODEL-->", "<!--SHEETS-->")

errors: list[tuple[Path | None, int, str]] = []


def error(path: Path | None, msg: str, line: int = 0) -> None:
    errors.append((path, line, msg))


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def frontmatter(path: Path) -> tuple[dict[str, str], int]:
    """The simple `key: value` frontmatter these files use, and the line the body starts on."""
    lines = path.read_text(encoding="utf-8").split("\n")
    if not lines or lines[0].strip() != "---":
        error(path, "no frontmatter (the file must start with ---)", 1)
        return {}, 0
    data: dict[str, str] = {}
    for i, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            return data, i
        m = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if m:
            data[m.group(1)] = m.group(2).strip()
    error(path, "frontmatter is not closed with ---", 1)
    return data, 0


def line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


# ---------------------------------------------------------------- inventory


def inventory() -> tuple[dict[str, list[Path]], dict[str, list[Path]]]:
    skills: dict[str, list[Path]] = {}
    agents: dict[str, list[Path]] = {}
    for skill_md in sorted(PLUGINS.glob("*/skills/*/SKILL.md")):
        skills.setdefault(skill_md.parent.name, []).append(skill_md)
    for agent_md in sorted(PLUGINS.glob("*/agents/*.md")):
        agents.setdefault(agent_md.stem, []).append(agent_md)
    return skills, agents


# ---------------------------------------------------------------- frontmatter


def check_skill(skill_md: Path) -> None:
    fm, body_start = frontmatter(skill_md)
    name, description = fm.get("name", ""), fm.get("description", "")
    if name != skill_md.parent.name:
        error(skill_md, f"name '{name}' does not match its folder '{skill_md.parent.name}'", 2)
    if not NAME_RE.match(name) or len(name) > 64:
        error(skill_md, f"name '{name}' must be lowercase words joined by hyphens, at most 64 characters", 2)
    if "anthropic" in name or "claude" in name:
        error(skill_md, f"name '{name}' may not contain 'anthropic' or 'claude'", 2)
    check_description(skill_md, description)
    body_lines = len(skill_md.read_text(encoding="utf-8").split("\n")) - body_start
    if body_lines > MAX_SKILL_LINES:
        error(skill_md, f"body is {body_lines} lines; keep SKILL.md under {MAX_SKILL_LINES} and move detail to references/")


def check_agent(agent_md: Path) -> None:
    fm, _ = frontmatter(agent_md)
    if fm.get("name") != agent_md.stem:
        error(agent_md, f"name '{fm.get('name', '')}' does not match its file name '{agent_md.stem}'", 2)
    check_description(agent_md, fm.get("description", ""))


def check_description(path: Path, description: str) -> None:
    if not description:
        error(path, "description is empty; it is what decides when this triggers", 3)
    elif len(description) > MAX_DESCRIPTION:
        error(path, f"description is {len(description)} characters; the limit is {MAX_DESCRIPTION}", 3)
    elif re.search(r"<[A-Za-z/][^>]*>", description):
        error(path, "description contains an XML/HTML tag", 3)


# ---------------------------------------------------------------- references


PATH_REF = re.compile(r"`((?:\.\./)*(?:[\w.-]+/)*(?:references|templates|scripts|assets)/[^`\s]*)`")
NAME_REF = re.compile(r"`([a-z0-9]+(?:-[a-z0-9]+)+)`\s+(skill|agent)\b")
MD_LINK = re.compile(r"\]\(([^)\s]+)\)")


def check_references(path: Path, skills: dict, agents: dict) -> None:
    text = path.read_text(encoding="utf-8")
    plugin = path.relative_to(PLUGINS).parts[0] if PLUGINS in path.parents else None
    bases = [path.parent]
    if plugin:
        bases += [PLUGINS / plugin] + sorted((PLUGINS / plugin / "skills").glob("*/"))

    for m in PATH_REF.finditer(text) if plugin else ():  # outside plugins, folder names are prose
        ref = m.group(1)
        if any(c in ref for c in "<>*{}$"):
            continue  # a placeholder or a pattern, not a file
        if not any((b / ref).exists() for b in bases):
            error(path, f"refers to `{ref}`, which does not exist next to this file or in plugin '{plugin}'",
                  line_of(text, m.start()))

    for m in NAME_REF.finditer(text):
        name, kind = m.group(1), m.group(2)
        known = skills if kind == "skill" else agents
        if name not in known and name not in EXTERNAL_NAMES:
            error(path, f"names the `{name}` {kind}, but no {kind} by that name exists in this marketplace",
                  line_of(text, m.start()))

    for m in MD_LINK.finditer(text):
        target = m.group(1).split("#")[0]
        if not target or re.match(r"^[a-z]+:", target) or any(c in target for c in "<>"):
            continue
        if not (path.parent / target).exists():
            error(path, f"link to '{target}' does not resolve", line_of(text, m.start()))


# ---------------------------------------------------------------- manifests


def check_manifests(base: str | None) -> None:
    market = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    listed = {p["name"]: p for p in market.get("plugins", [])}
    on_disk = {p.name for p in PLUGINS.iterdir() if (p / ".claude-plugin" / "plugin.json").exists()}
    for name in sorted(on_disk - listed.keys()):
        error(MARKETPLACE, f"plugin '{name}' exists in plugins/ but is not listed")
    for name, entry in sorted(listed.items()):
        source = (ROOT / entry.get("source", "")).resolve()
        manifest = source / ".claude-plugin" / "plugin.json"
        if not manifest.exists():
            error(MARKETPLACE, f"'{name}' has source '{entry.get('source')}', which has no .claude-plugin/plugin.json")
            continue
        plugin = json.loads(manifest.read_text(encoding="utf-8"))
        for key in ("name", "version", "description"):
            if plugin.get(key) != entry.get(key):
                error(manifest, f"{key} is {plugin.get(key)!r} here but {entry.get(key)!r} in marketplace.json")
        if base:
            check_version_bump(source, manifest, plugin.get("version"), base)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def check_version_bump(source: Path, manifest: Path, version: str | None, base: str) -> None:
    folder = rel(source)
    merge_base = git("merge-base", base, "HEAD").strip()
    # README.md is for people browsing the repository; Claude never loads it, so it needs no release.
    changed = [f for f in git("diff", "--name-only", merge_base, "--", folder).split() if Path(f).name != "README.md"]
    if not changed:
        return
    try:
        old = json.loads(git("show", f"{merge_base}:{rel(manifest)}")).get("version")
    except subprocess.CalledProcessError:
        return  # a new plugin
    if old == version:
        error(manifest, f"{len(changed)} file(s) under {folder} changed since {base}, but the version is still "
                        f"{version}; bump it (in marketplace.json too) or installed copies never update")


# ---------------------------------------------------------------- READMEs


def check_readmes(skills: dict, agents: dict) -> None:
    root_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for kind, items in (("skill", skills), ("agent", agents)):
        for name, paths in items.items():
            for path in paths:
                plugin_dir = PLUGINS / path.relative_to(PLUGINS).parts[0]
                if f"`{name}`" not in root_readme:
                    error(ROOT / "README.md", f"the {kind} `{name}` ({plugin_dir.name}) is not mentioned")
                readme = plugin_dir / "README.md"
                if readme.exists() and name not in readme.read_text(encoding="utf-8"):
                    error(readme, f"the {kind} `{name}` is not mentioned")


# ---------------------------------------------------------------- feature-workflow diagram palette


def check_diagram_palette() -> None:
    fd = PLUGINS / "feature-workflow" / "skills" / "feature-design"
    guide, render = fd / "references" / "diagrams.md", fd / "references" / "render.html"
    if not guide.exists():
        return
    canonical = {}
    for m in re.finditer(r"^\s*classDef (\w+) (.+?)\s*$", guide.read_text(encoding="utf-8"), re.M):
        canonical[m.group(1)] = m.group(2)
    missing = [c for c in DIAGRAM_CLASSES if c not in canonical]
    if missing:
        error(guide, f"the class block is missing {', '.join(missing)}")
        return

    for md in sorted((PLUGINS / "feature-workflow").rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        for m in re.finditer(r"^\s*classDef (\w+) (.+?)\s*$", text, re.M):
            name, style = m.group(1), m.group(2)
            if name in canonical and style != canonical[name]:
                error(md, f"classDef {name} differs from references/diagrams.md; copy the class block unchanged",
                      line_of(text, m.start()))

    if render.exists():
        html = render.read_text(encoding="utf-8")
        light = re.search(r"light:\s*\{\s*cls:\s*\{(.*?)\}", html, re.S)
        if not light:
            error(render, "could not find the light palette's cls block")
        else:
            for name, style in re.findall(r"(\w+):\s*'([^']*)'", light.group(1)):
                if name in canonical and style != canonical[name]:
                    error(render, f"light palette '{name}' differs from the class block in references/diagrams.md")
            for name in DIAGRAM_CLASSES:
                if not re.search(rf"\b{name}:\s*'", light.group(1)):
                    error(render, f"light palette has no '{name}' class")
        dark = re.search(r"dark:\s*\{\s*cls:\s*\{(.*?)\}", html, re.S)
        for name in DIAGRAM_CLASSES:
            if not dark or not re.search(rf"\b{name}:\s*'", dark.group(1)):
                error(render, f"dark palette has no '{name}' class")
        skill = (fd / "SKILL.md").read_text(encoding="utf-8")
        for slot in RENDER_SLOTS:
            if slot not in html:
                error(render, f"slot {slot} is missing")
            elif slot not in skill:
                error(fd / "SKILL.md", f"the render step does not say what to put in {slot}")


# ---------------------------------------------------------------- data files and scripts


def check_files() -> None:
    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None
        print("note: PyYAML not installed; YAML files are not parsed", file=sys.stderr)
    for path in sorted(ROOT.rglob("*")):
        if ".git" in path.parts or "__pycache__" in path.parts or not path.is_file():
            continue
        try:
            if path.suffix == ".json":
                json.loads(path.read_text(encoding="utf-8"))
            elif path.suffix in (".yml", ".yaml") and yaml:
                list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
            elif path.suffix == ".py":
                compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except Exception as e:  # noqa: BLE001 - every parse failure is reported the same way
            error(path, f"does not parse: {str(e).splitlines()[0] if str(e) else e!r}")


# ---------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", help="git ref to compare against; plugins changed since it must bump their version")
    args = parser.parse_args()

    skills, agents = inventory()
    for name, paths in {**skills, **agents}.items():
        if len(paths) > 1:
            for p in paths:
                error(p, f"'{name}' is defined {len(paths)} times in this marketplace; names must be unique")
    for paths in skills.values():
        for p in paths:
            check_skill(p)
    for paths in agents.values():
        for p in paths:
            check_agent(p)
    for md in sorted(list(PLUGINS.rglob("*.md")) + [ROOT / "README.md"]):
        check_references(md, skills, agents)
    check_manifests(args.base)
    check_readmes(skills, agents)
    check_diagram_palette()
    check_files()

    gha = os.environ.get("GITHUB_ACTIONS") == "true"
    for path, line, msg in errors:
        where = rel(path) if path else "."
        if gha:
            print(f"::error file={where},line={line or 1}::{msg}")
        else:
            print(f"{where}{f':{line}' if line else ''}: {msg}")
    n_skills, n_agents = sum(map(len, skills.values())), sum(map(len, agents.values()))
    print(f"{'FAIL' if errors else 'ok'}: {n_skills} skills, {n_agents} agents, {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
