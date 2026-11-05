#!/usr/bin/env python3
"""Render every ```mermaid block in the repository with the Mermaid CLI, one block at a time.

    python3 tools/check_mermaid.py

A template whose diagram does not parse teaches every design built from it to be broken, and
GitHub shows a parse error instead of the drawing. Each block is rendered on its own so a failure
names the file and line. Needs Node (npx) and a Chrome; set PUPPETEER_EXECUTABLE_PATH to use an
installed one instead of letting Puppeteer download its own.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MERMAID_CLI = "@mermaid-js/mermaid-cli@11.17.0"
BLOCK = re.compile(r"^```mermaid[ \t]*\n(.*?)^```", re.S | re.M)


def blocks() -> list[tuple[Path, int, str]]:
    found = []
    for md in sorted(ROOT.rglob("*.md")):
        if ".git" in md.parts or "node_modules" in md.parts:
            continue
        text = md.read_text(encoding="utf-8")
        for m in BLOCK.finditer(text):
            found.append((md, text.count("\n", 0, m.start()) + 1, m.group(1)))
    return found


def main() -> int:
    todo = blocks()
    gha = os.environ.get("GITHUB_ACTIONS") == "true"
    failures = 0
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        config = tmpdir / "puppeteer.json"
        config.write_text(json.dumps({"args": ["--no-sandbox", "--disable-gpu"]}))
        for i, (path, line, source) in enumerate(todo):
            src, out = tmpdir / f"{i}.mmd", tmpdir / f"{i}.svg"
            src.write_text(source, encoding="utf-8")
            run = subprocess.run(
                ["npx", "--yes", MERMAID_CLI, "--quiet", "-p", str(config), "-i", str(src), "-o", str(out)],
                capture_output=True, text=True,
            )
            where = f"{path.relative_to(ROOT)}:{line}"
            if run.returncode == 0 and out.exists():
                print(f"ok    {where}")
                continue
            failures += 1
            detail = next((l for l in (run.stderr + run.stdout).splitlines() if "Error" in l or "error" in l),
                          (run.stderr or run.stdout).strip().splitlines()[-1:] or ["unknown error"])
            detail = detail if isinstance(detail, str) else detail[0]
            if gha:
                print(f"::error file={path.relative_to(ROOT)},line={line}::Mermaid does not render: {detail}")
            print(f"FAIL  {where}: {detail}")
    print(f"{'FAIL' if failures else 'ok'}: {len(todo)} diagram(s), {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
