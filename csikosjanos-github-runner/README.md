# GitHub Runner

Self-hosted **GitHub Actions organisation runner**, packaged as an Umbrel app.

- **Image:** [`myoung34/github-runner`](https://hub.docker.com/r/myoung34/github-runner) ([source](https://github.com/myoung34/docker-github-actions-runner))
- **App id:** `csikosjanos-github-runner`
- **Port:** 9200 (status page only — this app has no real web UI)

## Why an Umbrel app (and not just `docker run`)

On umbrelOS the root filesystem is a wiped-on-OTA overlay, and **umbreld removes
any container it doesn't manage on every boot**. A manually started runner
therefore disappears after a reboot/update. Packaged as an app, umbreld owns its
lifecycle and recreates it on boot — surviving reboots and OTA updates.

## Configuration (env vars)

Secrets are **not** committed. After installing, create the app's runtime `.env`
and restart the app:

```sh
sudo tee /home/umbrel/umbrel/app-data/csikosjanos-github-runner/.env >/dev/null <<'EOF'
ORG_NAME=YourOrg
ACCESS_TOKEN=github_pat_xxx
EOF
sudo chmod 600 /home/umbrel/umbrel/app-data/csikosjanos-github-runner/.env
```

| Variable | Required | Default | Notes |
|---|:---:|---|---|
| `ORG_NAME` | ✅ | — | GitHub org the runner registers to |
| `ACCESS_TOKEN` | ✅ | — | Fine-grained PAT, org → **Self-hosted runners = Read/Write** (auto-generates registration tokens) |
| `RUNNER_NAME` | | `rozsa-umbrel` | Name shown in GitHub |
| `RUNNER_SCOPE` | | `org` | `org` / `repo` / `ent` |
| `RUNNER_GROUP` | | `default` | Runner group |
| `LABELS` | | `self-hosted,linux,x64,umbrel` | Labels workflows target |
| `EPHEMERAL` | | `false` | `true` = de-register after each job |
| `DISABLE_AUTO_UPDATE` | | `true` | Pin the runner agent version |

## Using it from workflows

```yaml
jobs:
  build:
    runs-on: [self-hosted, umbrel]   # array = AND across labels
```

The image is **minimal** — jobs must bring their own toolchains via
`actions/setup-node`, `actions/setup-python`, etc. (these install at job time and
work fine on self-hosted). No `docker.sock` is mounted, so image-build jobs won't
work until that's added.

## Services

| Service | Image | Purpose |
|---|---|---|
| `runner` | `myoung34/github-runner:latest` | The runner agent |
| `server` | `nginx:alpine` | Minimal status page for the app_proxy upstream |
| `app_proxy` | (umbreld) | Umbrel reverse proxy → `server:80` |

## Logs

```sh
sudo docker logs -f csikosjanos-github-runner_runner_1
```

## Limitations

- Linux/x64 jobs only. Windows/macOS builds need their own runners (e.g. a
  Windows KVM VM on the box; a Mac as a self-hosted runner).
- The "Open" button shows a static status page, not a dashboard.
