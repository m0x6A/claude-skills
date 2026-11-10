# dockge

Deploy a repository's app to a self-hosted [Dockge](https://github.com/louislam/dockge) host, the way
you would want it done at 3 am: a pinned image, a port nobody else uses, secrets that never leave the
host, a check that the app really answers, and the previous tag written down for a rollback.

- **dockge-deploy**: finds the app's port, health route, environment and state in the repository;
  publishes the image to GHCR (or offers a publish workflow, `templates/publish-image.yml`), or builds it locally on this machine and sends it to the host over SSH (`docker pussh` when unregistry is installed, else `docker save | docker load`), with no registry at all; writes
  the stack's `compose.yaml` with a pinned tag, a free port, `.env` for secrets, `./data` volumes, a
  healthcheck and bounded logs; deploys only after a person approves the exact commands; proves the
  container is healthy, the port answers and the logs are clean; and records the deploy and its
  rollback tag. Works with plain Dockge (`docker compose` in the stacks folder), with a stacks folder
  kept in git, and with an `apps` helper CLI on the host when there is one.

## Install

```
/plugin install dockge@m0x6a
```

## Setup

The skill asks for and records the host's facts in `.claude/profiles/dockge.md` on first use: the
SSH alias of the Docker host, the stacks folder, the Dockge URL, the port range for apps, whether the
host is logged in to ghcr.io, and whether the stacks folder is backed up. You need key-based SSH to
the host. For private images, run `docker login ghcr.io` on the host once, with a token that has only
`read:packages`.
