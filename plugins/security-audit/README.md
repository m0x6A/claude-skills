# security-audit

A source-first security audit for any codebase: reconnaissance, coverage-led hunting with isolated
hunters, adversarial validation of every candidate, a schema-validated `findings.json`, independent
record verification, and target-neutral reports.

## Attribution

This plugin is a Claude Code packaging of **[cloudflare/security-audit-skill](https://github.com/cloudflare/security-audit-skill)**
by Cloudflare, Inc., the skill that seeded Cloudflare's vulnerability discovery harness (see
[Build your own vulnerability harness](https://blog.cloudflare.com/build-your-own-vulnerability-harness)).
The methodology, phase files, attack-class companions, schema and validators are Cloudflare's work,
used under the MIT licence. Their copyright notice and licence are kept in [LICENSE](LICENSE).
Questions about the method itself belong upstream; problems with this packaging belong in this
repository.

Vendored from upstream commit `c1c8a8c1471069fb0e188eeaff69b8e8db6564a8` (2026-09-14).

### Changes from upstream

Every file under `skills/security-audit/` is upstream's, unchanged, except `SKILL.md`:

- An attribution line under the title.
- **Platform terminology** maps the upstream roles to Claude Code: the Task tool is the Agent tool,
  the `research` role is this plugin's `security-researcher` agent, and the `general` role is the
  built-in `general-purpose` agent.
- **Universal execution safety** adds a note that Claude Code's Bash sandbox (`/sandbox`) does not by
  itself meet the skill's execution bar (no empty environment, no resource limits), so target code
  stays unexecuted unless the parent adds and confirms the missing controls.
- **Full audit setup** says where Claude Code shows the skill directory and how to run the two
  validators.

Added by this packaging: the `security-researcher` agent (`agents/security-researcher.md`), a
read-only agent (Read, Grep, Glob) for reconnaissance, coverage critics and Phase 5 verification, so
the "does not write files or run targets" rule is enforced by its tools rather than by its prompt.
It uses `model: inherit` so the whole audit runs on the model you chose.

## Install

```
/plugin install security-audit@m0x6a
```

Requires Node.js on `PATH` for the two zero-dependency validators.

## Use

Start Claude Code in the repository you want to audit, then ask:

```
security audit this codebase
find security vulnerabilities in ./src
do a quick security review, output to ~/audits/my-project
```

A direct audit or pen-test request runs the full six-phase workflow; a security question or a focused
review uses guidance mode and writes no files. Full audits write to
`~/security-audit-skill/<repo-name>/run-<N>` unless you name another directory outside the target.
Profiles are `quick`, `standard` (default) and `deep`; you can also set a budget in agent invocations.
A full audit launches many agents, so start with `quick` on a large repository.

## Updating from upstream

```bash
git clone --depth 1 https://github.com/cloudflare/security-audit-skill /tmp/sas
diff -r /tmp/sas/skills/security-audit plugins/security-audit/skills/security-audit
```

Copy the changed files over, re-apply the `SKILL.md` changes listed above, update the commit hash in
this README, and bump the plugin version.
