# GitHub Runner

Self-hosted **GitHub Actions runners with a web UI**, packaged as an Umbrel app.

- **Image:** `ghcr.io/csikosjanos/github-runner-manager` (built from [`manager/`](./manager) by
  [`.github/workflows/build-github-runner-manager.yml`](../.github/workflows/build-github-runner-manager.yml)),
  based on [`myoung34/github-runner`](https://github.com/myoung34/docker-github-actions-runner)
- **App id:** `csikosjanos-github-runner`
- **Port:** 9200 (web UI, behind the Umbrel login)

## Why an Umbrel app (and not just `docker run`)

On umbrelOS the root filesystem is a wiped-on-OTA overlay, and **umbreld removes
any container it doesn't manage on every boot**. Packaged as an app, umbreld owns
its lifecycle and recreates it on boot, so runners survive reboots and OTA updates.

## Using the UI

Open the app. Each runner card shows its status (`idle` = online and listening,
`busy: <job>`, `error`, `disabled`), scope, labels, and when its token was last
updated. Buttons: Stop/Start (persisted as enabled/disabled), Restart, Logs
(last 300 lines), Edit, Remove (also unregisters it from GitHub).

**Add runner** asks for name, scope (organisation, or one `owner/repo`), labels,
runner group (org only), ephemeral, enabled, and a **new** personal access token:

| Scope | Fine-grained PAT permission |
|---|---|
| Organisation | Organisation → **Self-hosted runners: Read and write** |
| Repository | Repository → **Administration: Read and write** |

Editing a runner restarts only that runner. If the name, target, labels, group,
ephemeral flag or token changed, it is unregistered first and registered again.

Workflows target runners by label:

```yaml
jobs:
  build:
    runs-on: [self-hosted, umbrel]   # array = AND across labels
```

## How the token is protected

- Stored in `app-data/csikosjanos-github-runner/data/secrets/<id>.pat`, mode
  0600, directory 0700, root only. `config.json` next to it holds everything
  else and never the token.
- The API accepts a token on add/edit but never returns it; the UI shows only
  "set, updated <time>". Log lines are masked for anything token-shaped.
- The token never reaches a runner. The manager uses it to request a short-lived
  registration token from GitHub and passes that to the runner through an
  environment variable (readable only by that runner's user, not via `ps`).
- Each runner runs as its own unprivileged user (uid 20000+id) in its own
  directory (mode 0700), so a job can't read the tokens or another runner's
  credentials. Jobs have no sudo (`no-new-privileges`, not in sudoers).
- The UI needs the Umbrel login (`PROXY_AUTH_ADD` left at its default, on).
  Changes also need an `X-Runner-UI` request header, so other sites can't
  submit forms to it in your browser.
- Limitation: other app containers on Umbrel's internal Docker network can
  reach the manager's port 8080 directly, without the Umbrel login. They still
  can't read tokens, but they could add, change or remove runners.

## Design: one container, N runner processes (no docker.sock)

Two options were considered for starting and stopping individual runners:

1. **One container per runner, created by the UI through the Docker API.** This
   needs `POST /containers/create`. A docker-socket-proxy can limit which
   endpoints are reachable, but it can't limit what gets created (privileged,
   host mounts), so this is still root on the box. The token would also end up
   in each container's environment, visible in `docker inspect`.
2. **One supervisor container running N `Runner.Listener` processes**
   (chosen). The image is `myoung34/github-runner` (the same job toolchain as
   1.x) plus `manager/manager.py`, which is Python stdlib only (about 550 lines)
   and serves `manager/index.html`. Each runner gets a copy of `/actions-runner`
   in `/runners/<id>` and its own user. Stopping or restarting a runner signals
   only that process. It needs no Docker access at all.

Runner state outside `/data` is rebuilt on container start: each runner
re-registers with `--replace`, which keeps the same name in GitHub. 1.x did the
same thing.

## Upgrading from 1.x (migration)

1.x read `ORG_NAME` / `ACCESS_TOKEN` from `app-data/csikosjanos-github-runner/.env`,
loaded into compose by an app-data `exports.sh`. umbreld's app-script doesn't
pass an env file to `docker compose`, but it does source
`${UMBREL_ROOT}/app-data/<app>/exports.sh` (still true in umbrelOS 2.0,
`legacy-compat/app-script` `source_app`).

On the first start of 2.x (no `data/config.json` yet), the manager reads that
`.env` through a read-only mount and creates **runner #1** with the 1.x values:
name `rozsa-umbrel`, org `ORG_NAME`, labels `self-hosted,linux,x64,umbrel`,
group `default`, not ephemeral. It registers with `--replace`, so the existing
GitHub registration is taken over and workflows keep working.

2.x doesn't use `exports.sh` or compose interpolation for secrets, so the store
doesn't ship an `exports.sh`. An existing one on the box is left in place
(updates don't delete it) and does no harm. After runner #1 shows `idle`, you
can delete the old `.env` and `exports.sh` so the token isn't stored twice:

```sh
sudo rm /home/umbrel/umbrel/app-data/csikosjanos-github-runner/{.env,exports.sh}
```

A fresh install starts with no runners; add them in the UI.

## Files

| Path | What |
|---|---|
| `docker-compose.yml` | `runner` service (manager + runners) and app_proxy → `:8080` |
| `manager/manager.py` | Supervisor + JSON API (`/api/runners`, `…/<id>`, `…/<id>/{start,stop,restart,logs}`) |
| `manager/index.html` | The UI (vanilla JS) |
| `manager/test_manager.py` | Tests with a fake runner binary and a fake GitHub API: `python3 -m unittest -v test_manager.py` |
| `manager/Dockerfile` | `FROM myoung34/github-runner:<pinned>` + the two files above |

To release: change the code, bump `version` in `umbrel-app.yml` **and** the
image tag in `docker-compose.yml`. The workflow builds and pushes
`ghcr.io/csikosjanos/github-runner-manager:<version>`.

## Logs

```sh
sudo docker logs -f csikosjanos-github-runner_runner_1   # all runners, prefixed [runner <id>]
```

## Limitations

- Linux/x64 jobs only. Windows/macOS builds need their own runners.
- Jobs run as an unprivileged user without sudo, so `apt-get install` in a job
  won't work. Use `setup-*` actions or tools that are already in the image.
- No `docker.sock`, so jobs can't build images.
- Runner auto-update is disabled (`--disableupdate`). Runner versions change
  with the base image tag in `manager/Dockerfile`.
