#!/usr/bin/env bash
# Run the checks CI runs (.github/workflows/validate.yml), locally, before you push.
#
#   tools/validate.sh            # everything
#   tools/validate.sh --fast     # skip the Mermaid render (needs Node and Chrome, takes a minute)
#
# Plugins changed since origin/main must bump their version; pass BASE=<ref> to compare elsewhere.
set -uo pipefail
cd "$(dirname "$0")/.."
status=0
step() { printf '\n== %s\n' "$1"; }

step "Skills, references, manifests, READMEs, diagram palette"
python3 tools/validate_skills.py --base "${BASE:-origin/main}" || status=1

step "claude plugin validate --strict"
if command -v claude >/dev/null; then
  claude plugin validate . --strict >/dev/null || { claude plugin validate . --strict; status=1; }
  for plugin in plugins/*/; do
    claude plugin validate "$plugin" --strict >/dev/null || { claude plugin validate "$plugin" --strict; status=1; }
  done
  echo "ok: marketplace and $(ls -d plugins/*/ | wc -l) plugins"
else
  echo "skipped: the claude CLI is not on PATH"
fi

step "Bundled script tests"
for tests in $(find plugins -type d -path '*/scripts/tests' | sort); do
  skill="${tests%/scripts/tests}"
  (cd "$skill" && python3 -m unittest discover -s scripts/tests 2>&1 | tail -1 | sed "s#^#$skill: #") || status=1
done

if [ "${1:-}" != "--fast" ]; then
  step "Mermaid diagrams render"
  if command -v npx >/dev/null; then
    chrome="$(command -v google-chrome || command -v chromium || true)"
    if [ -n "$chrome" ]; then export PUPPETEER_SKIP_DOWNLOAD=true PUPPETEER_EXECUTABLE_PATH="$chrome"; fi
    python3 tools/check_mermaid.py | grep -v '^ok    ' || status=1
  else
    echo "skipped: npx is not on PATH"
  fi
fi

printf '\n%s\n' "$([ $status -eq 0 ] && echo 'All checks passed.' || echo 'Some checks failed; see above.')"
exit $status
