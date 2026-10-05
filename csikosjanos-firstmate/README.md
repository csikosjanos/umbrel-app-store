# Firstmate

[firstmate](https://github.com/kunchenguid/firstmate) (by Kun Chen, MIT) in **tmux in the browser**, with a
small **web UI** for settings, packaged as an Umbrel app.

firstmate is an agent distro: you talk to one agent (the first mate), and it runs a crew of coding agents,
each in its own tmux window and git worktree. There is nothing to install: the cloned repo is the distro, and
you start a harness (Claude Code, Pi, OpenCode, …) inside it.

- **Image:** `ghcr.io/csikosjanos/firstmate-umbrel` (built from [`image/`](./image) by
  [`.github/workflows/build-firstmate.yml`](../.github/workflows/build-firstmate.yml)), amd64 only
- **App id:** `csikosjanos-firstmate`
- **Port:** 3777 (web UI, behind the Umbrel login)

## Using it

Open the app. The **Terminal** tab is a tmux session (`fm`) inside `~/firstmate`. On first use:

```sh
gh auth login        # or set GH_TOKEN in Settings
claude               # or: pi, opencode
```

Logins (`~/.claude`, `~/.config/gh`, …), projects and the firstmate clone all live in the persistent home
(`app-data/csikosjanos-firstmate/data` = `/root`). Closing the browser tab does not stop anything: the tmux
session keeps running, and reopening the app re-attaches to it. "open terminal in its own tab" gives the
terminal the full window.

Update firstmate with `git pull` in `~/firstmate` (or its `/updatefirstmate` skill); the update persists.
Upgrade a harness with `npm i -g <package>@latest` (for example `@anthropic-ai/claude-code`): npm installs go
to `~/.npm-global`, which is persistent and first on `PATH`, so they win over the version in the image.

## Settings

The **Settings** tab stores environment variables for the harnesses and tools:

| Setting | Notes |
|---|---|
| `GH_TOKEN` | Used by `gh`, and by `git` over HTTPS to github.com (the image sets `gh auth git-credential` as git's credential helper) |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY` | For the harnesses. Subscription logins (`claude` → `/login`, …) work without them |
| Git name / email | Exported as `GIT_AUTHOR_*` / `GIT_COMMITTER_*` (empty = use `git config`) |
| Custom variables | Any other `KEY=VALUE` (names like `PATH`, `HOME`, `BASH_ENV` are refused) |

**Values are write-only**: the API accepts them but never returns them, the page never renders them, and
nothing logs them. The UI only shows "set, updated <time>". To change one, enter a new value; to unset it,
Remove.

**Changes apply to new shells.** Open a new tmux window (`Ctrl-b c`) or run `source /settings/env.sh` in an
existing shell. Agents that are already running keep the values they started with; restart them to pick up a
change. Commands started by tmux or by scripts (`bash -c …`, crewmate windows) re-read the settings
automatically (`BASH_ENV`).

## Architecture

```
browser ──Umbrel login──▶ umbreld app gateway (:3777)
                               │
                               ▼
                 web  (python3 server.py :8080)          fm  (tini → ttyd → tmux → bash)
                 ├─ /            Settings UI              ├─ /root      ◀── app-data/data
                 ├─ /api/...     settings API             ├─ /settings  ◀── app-data/settings (read-only)
                 └─ /terminal/   proxy (HTTP + WebSocket) ─UNIX socket─▶ ttyd --interface /run/fm/ttyd.sock
                     ▲ app-data/settings (rw)                           (app-data/run, shared)
```

- **One image, two services.** `fm` runs the terminal, `web` runs `python3 /opt/firstmate-web/server.py` from
  the same image: one build, one package to publish, no extra disk (shared layers). `web` gets no access to the
  home volume, drops all capabilities except `DAC_OVERRIDE`/`FOWNER`, and has small limits.
- **The terminal has no TCP port.** ttyd listens on a UNIX socket in `app-data/run`, which only the two
  containers mount. Other apps on `umbrel_main_network` cannot reach the shell, and nothing is published.
- **Settings flow:** web UI → `settings/settings.json` (0600, the store) → generated `settings/env.sh`
  (0600, `export KEY='value'` lines, plus `unset` for removed keys) → mounted read-only into `fm` at
  `/settings` → sourced by every bash via `BASH_ENV` and `/etc/bash.bashrc`, and by the tmux server when
  the first browser connects.

## Security

- Umbrel login stays on (`PROXY_AUTH_ADD` not set). The terminal is a **root shell inside the `fm`
  container** behind that login. There is no `docker.sock`, no host mount beyond app-data, no
  `privileged`, `no-new-privileges` on both services.
- The web server refuses every request (GET included) that does not come from Umbrel's app gateway. On
  umbrelOS 2.x the gateway runs inside umbreld on the host and connects from the Docker bridge gateway;
  other app containers arrive from their own IPs and get 403. Trusted peers are **IPs only**: loopback,
  the container's default gateway(s), and `EXTRA_ALLOWED_PEERS` (comma-separated IPs, unset by default).
  No container name is resolved: `csikosjanos-firstmate_app_proxy_1` does not exist on umbrelOS 2.x, so
  another app's container could claim that name or alias on the shared network.
- Mutating API calls need an `X-Firstmate-UI: 1` header (a cross-site form or fetch cannot set it without a
  CORS preflight, which is never granted).
- The terminal WebSocket needs a **terminal token** (cross-site WebSocket hijacking). The web server
  generates a random token at start, embeds it only in the UI page (readable same-origin only; the CSP
  blocks foreign scripts), and the page opens ttyd at `terminal/?fm_token=…`; ttyd's client carries that
  query into its WebSocket URL, and the proxy compares it in constant time. Every upgrade needs it, browser
  or not. `Origin` and cookies are deliberately not trusted: another Umbrel app on the same host (different
  port) is same-site, so `SameSite` cookies would be sent from its pages. The token rotates when `web`
  restarts (reload the app), is never logged, and is not passed on to ttyd.
- Only ttyd's read-only HTTP endpoints (`/terminal`, `/terminal/`, `/terminal/token`) are proxied; every
  other `/terminal/...` path is 404. ttyd runs without a credential, so `/terminal/token` returns an empty
  token; the shell is only reachable through the token-guarded WebSocket.
- Secrets: `settings/` is 0700, its files 0600. Harness logins in `data/` are as safe as the box's disk.
  This repo is public: never commit anything from app-data.

## Resources

| Service | CPU | Memory | PIDs | Other |
|---|---|---|---|---|
| `fm` | 12 | 24 GB | 16384 | `shm_size: 1g` |
| `web` | 0.5 | 256 MB | 256 | |

Generous for a crew of agents, but bounded so the production GitHub runner on the same box (20 threads,
62 GB) keeps headroom. Change them in `docker-compose.yml` if needed.

## What is in the image

Pinned in [`image/Dockerfile`](./image/Dockerfile): Node 22 (Debian bookworm, by digest), ttyd 1.7.7 and
gh 2.102.0 (sha256-checked release binaries), Claude Code 2.1.289 (`@anthropic-ai/claude-code`), Pi 1.0.3
(`@earendil-works/pi-coding-agent`), OpenCode 1.18.34 (`opencode-ai`), plus tmux, git, jq, python3, perl,
build-essential, ripgrep and the other helpers firstmate's scripts use. firstmate itself is **not** in the
image: it is cloned into `~/firstmate` on first start, at a pinned commit, on its `main` branch.

firstmate offers to install the optional tools it wants (treehouse, no-mistakes, gh-axi, …) the first time
it runs; `npm -g` and `~/.local/bin` installs persist. `apt-get install` does not survive an app update or
restart of the container.

## Releasing

Change `image/`, bump `version` in `umbrel-app.yml` and the image tag in `docker-compose.yml` (both
services), and merge: the workflow pushes `ghcr.io/csikosjanos/firstmate-umbrel:<version>` from `main`. PRs
run the unit tests, a local build and a smoke test (ttyd through the web container, write-only settings,
CSRF, sibling container refused) without pushing.
