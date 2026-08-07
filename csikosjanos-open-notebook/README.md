# Open Notebook

A self-hosted, privacy-first alternative to Google's **NotebookLM**. Organise
sources and notes into notebooks, then use AI to summarise, chat over your
material, extract insights, and generate podcasts — all on your own hardware.

Upstream project: **https://github.com/lfnovo/open-notebook** (by Luis Novo).

## What you get

- **Web UI** on port `8502` (the app's front door in Umbrel)
- **REST API** on port `5055` (for CLI/automation)
- **SurrealDB** database (RocksDB), bound to `127.0.0.1:8000` — internal only

Both the database and your notebook data persist under the app's data
directory, so they survive restarts and updates.

## Model providers

Open Notebook talks to 18+ providers for chat / embeddings / speech, including
**Anthropic, OpenAI, Google GenAI, Groq, Mistral, DeepSeek, xAI, Cohere,
ElevenLabs, Deepgram** and **Ollama**.

On this box you can point it at the local **GPU Ollama** for fully offline use,
or paste cloud API keys in the UI for frontier models. Keys entered in the UI
are encrypted at rest with your `OPEN_NOTEBOOK_ENCRYPTION_KEY` (see below).

## First-run setup — set your secrets

The app installs with insecure defaults. **Before real use**, set proper
secrets in the app's data-dir `.env` and restart.

On the box:

```sh
# 1. Generate secrets
openssl rand -hex 32   # -> use as OPEN_NOTEBOOK_ENCRYPTION_KEY
openssl rand -hex 16   # -> use as SURREAL_PASSWORD

# 2. Write them to the app-data env file (created by umbreld on install).
#    API_URL is REQUIRED — set it to the URL you actually open the app on
#    (no /api suffix). If you expose it via Tailscale Serve on port+10000,
#    that's https://<host>.ts.net:18502 .
cat >> ~/umbrel/app-data/csikosjanos-open-notebook/.env <<'EOF'
API_URL=https://<host>.ts.net:18502
OPEN_NOTEBOOK_ENCRYPTION_KEY=<paste 32-byte hex>
SURREAL_USER=onbadmin
SURREAL_PASSWORD=<paste 16-byte hex>
EOF

# 3. Restart the app from the Umbrel UI (or: umbreld client apps.restart ...)
```

> ⚠️ **`API_URL` is not optional.** open-notebook's browser frontend calls the
> API directly, so it must know the app's public address. Left unset, the
> notebooks page shows **"Unable to Connect to API Server"**. Use the exact URL
> you open in the browser (scheme + host + port, **no** `/api`). Next.js
> forwards `/api/*` to the backend internally, so only this one URL is needed.

> ⚠️ **Do not change `OPEN_NOTEBOOK_ENCRYPTION_KEY` after first use.** It
> encrypts the provider API keys you save in the UI; rotating it makes those
> keys unreadable and you'll have to re-enter them.

> ⚠️ If you set `SURREAL_USER`/`SURREAL_PASSWORD` **after** the DB has already
> initialised with the `root/root` default, the new credentials won't match the
> existing datastore. Set them **before first launch**, or wipe
> `~/umbrel/app-data/csikosjanos-open-notebook/data/surreal_data` to re-init.

## Environment variables

| Variable | Purpose | Secret? |
|---|---|---|
| `API_URL` | **Required.** Public URL the browser reaches the app on (no `/api`). | no |
| `OPEN_NOTEBOOK_ENCRYPTION_KEY` | Encrypts provider API keys stored in the UI. Must be stable. | ✅ yes |
| `SURREAL_USER` | SurrealDB username | ✅ yes |
| `SURREAL_PASSWORD` | SurrealDB password | ✅ yes |
| `SURREAL_URL` | DB endpoint (`ws://surrealdb:8000/rpc`) — internal, fixed | no |
| `SURREAL_NAMESPACE` / `SURREAL_DATABASE` | Logical DB names (`open_notebook`) | no |

Provider API keys (Anthropic, OpenAI, …) are entered **in the Web UI**, not
here.

## Data & persistence

| Volume | Host path | Contents |
|---|---|---|
| `surreal_data` | `app-data/.../data/surreal_data` | SurrealDB RocksDB files |
| `notebook_data` | `app-data/.../data/notebook_data` | Notebooks, sources, generated assets |

## Notes / limitations

- CPU-only app containers; heavy generation is offloaded to whatever model
  provider you configure (local Ollama GPU or cloud).
- Tailscale HTTPS exposure follows the store's `+10000` scheme
  (`tailscale serve --https=18502 localhost:8502`) if you want remote access.
- The REST API on `5055` has no auth in front of it beyond Umbrel's
  `app_proxy`; keep it on the tailnet/LAN, not the public internet.

Packaged for the **Csikos Janos** Umbrel community app store by `csikosjanos`.
