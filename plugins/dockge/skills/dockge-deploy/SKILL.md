---
name: dockge-deploy
description: Deploy the current repository's app to a self-hosted Dockge host over SSH — publish the image to GHCR (or reuse one), write or update the Compose stack in Dockge's stacks folder, pick a free port, keep secrets in the stack's .env on the host, deploy only after a person approves the exact commands, then prove it runs (container healthy, port answers, logs clean) and record how to roll back. Reads and writes `.claude/profiles/dockge.md`. Use when asked to deploy, ship, host or run an app on Dockge, on the apps VM, on the homelab or on a home server, to update a running stack to a new image, or to roll one back.
---

# Deploy to Dockge

Dockge is a web UI over a folder of Compose stacks: every app is
`<stacks>/<name>/compose.yaml` on the host, and Dockge shows whatever is in that
folder. So the folder is the truth. This skill changes the folder (or the git repo
behind it), runs `docker compose`, and Dockge picks the stack up by itself.

The deploy itself is the easy part. What makes it safe is a pinned image tag, a
port nobody else uses, secrets that never leave the host, a check that the app
really answers, and the previous tag written down for a rollback.

## Rules

- **Read freely, change only with a yes.** Listing stacks, `docker ps`, logs and
  `curl` need no approval. Writing to the host, `deploy`, `restart`, `stop` and
  `docker login` happen only after the person approves the exact commands, shown
  in full. One approval may cover "write this compose file, then deploy".
- **Secrets stay on the host.** Never print, commit or pass a secret value on a
  command line. The stack's `.env` holds them, mode 600. You write the variable
  *names*; the person fills in the values.
- **Pin the image.** Deploy `sha-<short>` tags, not `latest`, so a rollback is
  "the previous tag" and `docker compose pull` can't change a running app by
  surprise.
- **Touch only this app's stack.** Never stop, edit or prune other stacks, and
  never run `docker system prune` or `docker volume rm`.
- **Git-managed stacks change in git.** If the stacks folder is a git clone, edit
  the stacks repo, push, and let the deploy pull. A hand edit on the host makes
  the next pull fail.

## 0. Profile

Read `.claude/profiles/dockge.md`. If it is missing, create it from
[templates/profile.md](templates/profile.md). Discover each fact read-only and ask
only for what you can't find:

1. **SSH host.** Ask which SSH alias reaches the Docker host (an `~/.ssh/config`
   entry such as `apps`), then `ssh -o BatchMode=yes <host> true`. If that asks
   for a password, stop: the person sets up key login first.
2. **Stacks folder.** Dockge's default is `/opt/stacks`. Confirm with
   `ssh <host> 'docker inspect $(docker ps -qf name=dockge) --format "{{range .Config.Env}}{{println .}}{{end}}"' | grep DOCKGE_STACKS_DIR`,
   or `ssh <host> ls /opt/stacks`.
3. **Helper CLI.** `ssh <host> 'command -v apps'`. Some setups ship a small
   wrapper (`apps new|deploy|ls|logs|stop`) that works on the same folder. Use it
   when present, plain `docker compose` otherwise.
4. **Stacks in git?** `ssh <host> 'git -C <stacks> remote get-url origin'`. If it
   prints a URL, ask where the person's local clone of that repo is.
5. **Registry login.** `ssh <host> 'grep -o "\"ghcr.io\"" ~/.docker/config.json'`
   (prints only the key, never the token). No match means the host can pull only
   public images.
6. **URLs and ports.** Ask for the Dockge URL and the host name apps are reached
   on (often `<host>.local`), and agree on a port range for apps, such as
   8081–8199.
7. **Backups.** Ask whether the host's stacks folder is backed up (a VM backup,
   restic, nothing). If nothing, say so in the report: `./data` then has no copy.

Every fact gets the date it was verified. Commit the profile with the change that
needs it.

## 1. Understand the app

From the repository, not from memory:

- **Container port.** `EXPOSE` in the Dockerfile, else the framework's default or
  the port the code listens on. The app must listen on `0.0.0.0`, not
  `127.0.0.1`, or nothing outside the container reaches it.
- **Health check.** A `/health`, `/healthz` or `/ready` route. If there is none,
  use a cheap page that returns 200 and suggest adding a real one.
- **Configuration.** Every environment variable the code reads
  (`process.env.X`, `os.environ["X"]`, `std::env::var("X")`,
  `Environment.GetEnvironmentVariable("X")`, `.env.example`). Mark which are
  secrets.
- **State.** Files the app writes (SQLite, uploads, caches). They need a volume
  under `./data`, or every deploy loses them.
- **No Dockerfile?** Propose one as its own change: multi-stage build, a
  non-root user, only the runtime in the final image. Don't deploy until the
  person has accepted it.

## 2. Image

1. **Is an image published already?** Look in `.github/workflows/` for
   `docker/build-push-action` or `docker push ghcr.io/...`.
2. **If not,** offer [templates/publish-image.yml](templates/publish-image.yml):
   on every push to `main` it pushes `ghcr.io/<owner>/<repo>:sha-<short>` and
   `:latest`, built for `linux/amd64`. Set `runs-on` from the profile (a
   self-hosted runner needs Docker; GitHub-hosted works too). It is a normal
   change: commit, push, let it run.
3. **Pick the tag.** The newest successful publish on `main`:
   `gh run list --workflow publish-image.yml --branch main --status success -L 1 --json headSha --jq '.[0].headSha[:7]'`
   gives `sha-<that>`. Check that the tag exists before you use it:
   `docker manifest inspect ghcr.io/<owner>/<repo>:sha-<short> >/dev/null`
   (on the host, if only the host is logged in).
4. **Private package and no registry login on the host:** the person runs
   `docker login ghcr.io` on the host once, with a token that has only
   `read:packages`. Never run it for them, and never put the token in a command
   you show.

## 3. Stack

1. **Name.** The repo name in lower case, `[a-z0-9_-]` only. It is the folder
   name and the Compose project name.
2. **Port.** List what is taken:
   `ssh <host> "docker ps --format '{{.Ports}}'"` and
   `ssh <host> "grep -h -A3 '^ *ports:' <stacks>/*/compose.yaml"`. Pick the
   first free port in the profile's range. A new app never takes a port another
   stack declares, even one that is stopped.
3. **Compose file.** Start from [templates/compose.yaml](templates/compose.yaml):
   - the pinned image
   - `restart: unless-stopped`
   - the port
   - `env_file: .env`
   - volumes under `./data`
   - a healthcheck
   - bounded logs (json-file, 3 × 10 MB), so a chatty app can't fill the disk

   The healthcheck runs inside the container, so it needs `wget` or `curl` in the
   image. For distroless or scratch images, leave it out and rely on the check
   in step 5.
4. **`.env`.** The variable names from step 1, without values, written with
   `umask 077`. List the names the person must fill in. Example:
   `ssh <host> 'umask 077; printf "DATABASE_URL=\nAPI_KEY=\n" > <stacks>/<name>/.env'`.
5. **Where the file goes.**
   - *Stacks in git:* add `<name>/compose.yaml` in the person's clone of the
     stacks repo, commit, push. `.env` is never committed. Check that the stacks
     repo's `.gitignore` has `.env`.
   - *Helper CLI:* `ssh <host> apps new <name> <image> <host>:<container>`
     scaffolds the folder. Then replace its `compose.yaml` with yours.
   - *Plain Dockge:* `ssh <host> 'mkdir -p <stacks>/<name>'`, then
     `ssh <host> 'cat > <stacks>/<name>/compose.yaml' < compose.yaml`.
6. **Show the person** the compose file, the list of `.env` names, the port, and
   every command from here to the deploy. Wait for a yes.

## 4. Deploy

After the yes, and after the person confirms `.env` has its values:

- Helper CLI: `ssh <host> apps deploy <name>` (it pulls the stacks repo first if
  there is one).
- Plain: `ssh <host> 'cd <stacks>/<name> && docker compose pull && docker compose up -d --remove-orphans'`.

For an update to a running stack: change only the `image:` tag, then deploy the
same way. Write down the tag that was running before; it is the rollback.

## 5. Prove it works

Don't report success until all four checks pass:

1. **Running and healthy.** `ssh <host> 'cd <stacks>/<name> && docker compose ps --format "{{.Name}} {{.State}} {{.Health}}"'`.
   Wait up to the healthcheck's `start_period` plus three intervals for
   `healthy`. A state of `restarting` means it is crash-looping: go to the logs.
2. **It answers from outside.** `curl -fsS -o /dev/null -w '%{http_code}\n' http://<app-host>:<port><health>`
   from this machine, expecting 200.
3. **Clean logs.** `ssh <host> 'cd <stacks>/<name> && docker compose logs --since 5m'`.
   Look for `error`, `panic`, `exception`, `fatal`, `refused`, and quote any
   matches.
4. **Dockge shows it.** The stack appears at the Dockge URL. It scans the folder;
   a refresh is enough.

Then report:

| | |
| --- | --- |
| Stack | name, image tag, previous tag |
| URL | `http://<app-host>:<port>` |
| Health | state and HTTP status |
| Logs | clean, or the matching lines |
| `.env` | names still empty, if any |

Add a row to the profile's **Deploys** table: date, tag, previous tag, result.

## 6. Roll back

Set `image:` back to the previous tag from the Deploys table (or `git revert` in
the stacks repo), get a yes, deploy, and run step 5 again. If the new version
changed the data in `./data` (a migration), say so: a rollback of the image does
not roll back the data.

## When it goes wrong

| Symptom | Usual cause | Fix |
| --- | --- | --- |
| `pull access denied`, `unauthorized` | Private package, host not logged in to ghcr.io | Person runs `docker login ghcr.io` on the host with a `read:packages` token |
| `manifest unknown` | Tag never published | Check the publish run; use a tag from step 2.3 |
| `port is already allocated` | Port taken by another stack or process | Pick the next free port (step 3.2) |
| `exec format error` | Image built for arm64 | Build `linux/amd64` (`platforms:` in the workflow) |
| `restarting` loop | Missing env value, crash on start | Logs; compare `.env` names with step 1 |
| `healthy` but `curl` fails | App listens on 127.0.0.1, or a firewall | Listen on `0.0.0.0`; check the host's firewall for the port |
| Stack not in Dockge | Wrong folder or file name | Must be `<stacks>/<name>/compose.yaml` (or `docker-compose.yml`), one level deep |
| Disk filling up | Unbounded logs or old images | Bounded logging (template); the person decides on pruning old images |

## Design for 3 am

If this app broke at 3 am, on-call needs: the stack name and URL (the report),
the logs (`apps logs <name> -f` or `docker compose logs -f`, or the stack in
Dockge), the last good tag (the Deploys table), and to know whether `./data` is
backed up (the profile). Make sure all four are written down before you call the
deploy done.
