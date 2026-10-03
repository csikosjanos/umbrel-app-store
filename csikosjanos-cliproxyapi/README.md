# CLIProxyAPI (Plus fork)

Self-hosted AI API proxy: many upstream providers behind one OpenAI/Claude/Gemini-compatible API, with your own client keys. This build adds a passthrough for TypeSafe System One decision requests (`POST /v1/systemone`) and ships the CPAMC web console.

- **Upstream:** <https://github.com/jc01rho/CLIProxyAPIPlus> (fork of [router-for-me/CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI))
- **Image:** `ghcr.io/csikosjanos/cliproxyapi-plus:v8.0.9-2` (pinned; self-built from the fork's `Dockerfile` by [`.github/workflows/build-cliproxyapi.yml`](../.github/workflows/build-cliproxyapi.yml))
- **Port:** `8317` → container `8317` via Umbrel's `app_proxy`
- **Web UI:** `http://umbrel.local:8317/management.html` (the Umbrel "Open" button goes there)
- **Data:** `~/umbrel/app-data/csikosjanos-cliproxyapi/data` → `/data` (`config.yaml`, `auths/`, `logs/`, `static/`)
- **App version:** store-versioned (`1.0.0`); the pinned upstream release is CLIProxyAPIPlus `v8.0.9-2`

## Why this fork

Upstream CLIProxyAPI has no System One support: the request ([issue #6012](https://github.com/router-for-me/CLIProxyAPI/issues/6012)) was converted to Ideas [discussion #6045](https://github.com/router-for-me/CLIProxyAPI/discussions/6045) with no maintainer reply.

The jc01rho fork adds a simple passthrough (`sdk/api/handlers/openai/openai_systemone_handlers.go`):

- `POST /v1/systemone` with a native System One body (`model` + `questions`).
- The upstream is chosen by `model` through the normal `openai-compatibility` provider list.
- The body is forwarded **unchanged** to `<base-url>/v1/systemone` (a trailing `/v1` on the base URL is not doubled), and the raw upstream JSON comes back.
- OpenRouter: base `https://openrouter.ai/api/v1` → `https://openrouter.ai/api/v1/systemone`. Models e.g. `typesafe/jev-1.13`, `~typesafe/jev-latest`.

It is also the most active fork (thousands of commits ahead of upstream).

## Keys at a glance

| Key | What it is | Where it comes from | Where to find it |
|---|---|---|---|
| Management key | Logs you into the web UI / `/v8/management` API | `MANAGEMENT_PASSWORD` = Umbrel's per-install app password (`deterministicPassword: true`) | Umbrel dashboard → app → shown password |
| Client API key | What your apps send to the proxy (`Authorization: Bearer …`) | Random `sk-…`, generated once on first start | Web UI → Config (`access.api-keys`), or `data/config.yaml` |
| Provider key | Your OpenRouter / other upstream key | You add it | Web UI → AI Providers, or `data/config.yaml` |

None of these are in this repo.

## First run

1. Install the app from the store and start it. On first start the container copies [`default-config.yaml`](./default-config.yaml) to `data/config.yaml`, putting a random client key into `access.api-keys`. It never overwrites an existing `config.yaml`.
2. Open the app from the Umbrel dashboard. The CPAMC console loads at `/management.html`. On first access the proxy downloads `management.html` from the [jc01rho/Cli-Proxy-API-Management-Center](https://github.com/jc01rho/Cli-Proxy-API-Management-Center) releases into `data/static/`, so the box needs internet then.
3. Log in with the **management key** = the password Umbrel shows for this app. The API base is the same origin (`http://umbrel.local:8317`).
4. Add OpenRouter: **AI Providers → OpenAI compatible → add**, or edit `data/config.yaml`:

   ```yaml
   api-keys:
     openai-compatibility:
       - name: "openrouter"
         base-url: "https://openrouter.ai/api/v1"
         keys:
           - api-key: "sk-or-v1-…"
         models:
           - name: "typesafe/jev-1.13"
           - name: "~typesafe/jev-latest"
   ```

   Config changes hot-reload; no restart needed.
5. Copy the **client API key** from Config (`access.api-keys`) and test:

   ```bash
   curl -s http://umbrel.local:8317/v1/systemone \
     -H "Authorization: Bearer sk-…client-key…" \
     -H "Content-Type: application/json" \
     -d '{"model":"typesafe/jev-1.13","questions":{ … }}'
   ```

### Model names: unique per provider, no alias for System One

- **One provider per model name.** If the same name (or alias) is listed under two providers, the proxy may serve a request from either, or fail over between them, without telling you which upstream answered. That concern was raised in discussion #6045. Give each provider distinct names.
- **No alias for System One models.** `/v1/systemone` forwards the body unchanged, so the `model` your client sends is what the upstream receives. Use the real upstream id (`typesafe/jev-1.13`), not an alias.

## Configuration

| Setting | Value in the seeded config | Why |
|---|---|---|
| `server.port` | `8317` | matches the manifest port |
| `management.allow-remote` | `true` | the browser is outside the container (`MANAGEMENT_PASSWORD` also forces this) |
| `management.secret-key` | `""` | key comes from `MANAGEMENT_PASSWORD`; a value here would be an extra, bcrypt-hashed key |
| `access.api-keys` | one random `sk-…` | client key; add more per client |
| `oauth.auth-dir` | `/data/auths` | OAuth/auth files persist |
| `observability.logs.logging-to-file` | `true` | the CPAMC Logs page reads the log files |
| `observability.logs.logs-max-total-size-mb` | `200` | caps disk use |
| `observability.usage.usage-statistics-enabled` | `true` | CPAMC dashboard stats (in memory, reset on restart) |
| providers | none | commented OpenRouter example in the file |

### Environment variables (compose)

| Variable | Set by | Purpose |
|---|---|---|
| `MANAGEMENT_PASSWORD` | compose, `${APP_PASSWORD}` | management key; enables management routes + remote access |
| `WRITABLE_PATH` | compose, `/data` | puts `logs/`, `static/`, discovery state under the data dir |
| `TZ` | compose, `${TZ:-Etc/UTC}` | the image bakes in `Asia/Shanghai`; override via `~/umbrel/app-data/csikosjanos-cliproxyapi/.env` |

## Ports

Only `8317` (API + web UI) is exposed. The fork's own compose also publishes OAuth callback ports `8085/1455/54545/51121/11451`. They are left out here because:

- API-key upstreams (OpenRouter, any OpenAI-compatible endpoint) need none of them.
- Those callbacks redirect to `localhost:<port>` on the machine running the browser, which is your laptop, not the box. For OAuth logins started from the web UI, the management API accepts the pasted redirect URL instead (`/v0/management/oauth-callback`). This flow is untested in this app.

## Remote access over Tailscale

Following the `+10000` convention used by the other apps in this store:

```bash
tailscale serve --bg --https=18317 localhost:8317
```

Then `https://<host>.ts.net:18317/management.html`.

## Security

- **LAN / tailnet only.** Anyone with a client key spends your provider credit; anyone with the management key can read and change provider keys. Do not port-forward 8317 to the internet.
- **Umbrel login is off** (`PROXY_AUTH_ADD: "false"`), because API clients cannot do Umbrel's login. The proxy's own keys are the only gate.
- **"Remember password" in CPAMC** stores the management key in browser storage **obfuscated, not encrypted** (per the CPAMC README). Don't tick it on shared machines.
- Management requests are rate-limited per IP; repeated wrong keys get the IP banned temporarily.

## Notes and limitations

- **Self-built image.** The fork publishes no container image (its compose references `eceasy/cli-proxy-api-plus`, a different build). The store's workflow builds `ghcr.io/csikosjanos/cliproxyapi-plus:<tag>` for `linux/amd64` only. To bump: change the workflow's default tag (pushing rebuilds), then the compose image tag and the app version.
- **Web UI is fetched at runtime and auto-updates.** `management.html` comes from the CPAMC fork's latest release, not from the pinned image, and the proxy checks for updates periodically. A newer UI could expect a newer backend. To freeze it, set `management.disable-auto-update-panel: true`.
- **Config is only seeded once.** App updates never touch `data/config.yaml`; compare with `default-config.yaml` (in the app dir) after an update if needed.
- **No GPU, no Ollama dependency.** To route to local models, add the Ollama app as an OpenAI-compatible provider (`http://ollama_ollama_1:11434/v1`).
