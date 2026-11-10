# Dockge profile

What the `dockge-deploy` skill needs to know about where this repository's app runs.
Every fact carries the date it was last verified. Secret values never go here, only
variable names.

## Host

| Fact | Value | Verified |
| --- | --- | --- |
| SSH host (alias in `~/.ssh/config`) | `apps` | YYYY-MM-DD |
| Stacks folder | `/opt/stacks` | YYYY-MM-DD |
| Dockge UI | `http://apps.local:5001` | YYYY-MM-DD |
| Host name apps are reached on | `apps.local` | YYYY-MM-DD |
| Helper CLI | `apps` / none (plain `docker compose`) | YYYY-MM-DD |
| Stacks in git | no / `git@github.com:OWNER/stacks.git`, local clone at `~/src/stacks` | YYYY-MM-DD |
| Logged in to ghcr.io on the host | yes / no | YYYY-MM-DD |
| Port range for apps | 8081–8199 | YYYY-MM-DD |
| Stacks folder backed up | nightly VM backup / restic / no | YYYY-MM-DD |

## Build

| Fact | Value |
| --- | --- |
| Image | `ghcr.io/OWNER/REPO` |
| Publish workflow | `.github/workflows/publish-image.yml` |
| Runner | `ubuntu-latest` / `[self-hosted, LABEL]` |
| Platform | `linux/amd64` |

## App

| Fact | Value |
| --- | --- |
| Stack name | `repo` |
| Container port | `8080` |
| Host port | `8081` |
| Health check | `GET /health` → 200 |
| Environment (names only; values live in `<stacks>/<name>/.env` on the host) | `DATABASE_URL`, `API_KEY` (secret) |
| Persistent data | `./data` → `/data` |

## Deploys

| Date | Tag | Previous tag | Result |
| --- | --- | --- | --- |
| YYYY-MM-DD | `sha-abc1234` | — | healthy, 200 on `/health` |
