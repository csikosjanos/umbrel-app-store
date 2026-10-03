# Ollama Model Manager

Web UI for managing the models of the Ollama app on this box: what is loaded, unload/load, installed models with details, and downloads from the Ollama library or Hugging Face. Management tool, not a chat app.

- **Upstream:** <https://github.com/mophead64/ollama-model-manager> (MIT)
- **Image:** `ghcr.io/mophead64/ollama-model-manager:2026.10.01.1@sha256:0bf7a430…92fd7` (upstream image, pinned by digest; build provenance attested to upstream commit `b8355b8`)
- **Port:** `11435` → container `8080` via Umbrel's `app_proxy`
- **Data:** `~/umbrel/app-data/csikosjanos-ollama-model-manager/data` → `/data` (`omm.db`, SQLite)
- **Depends on:** the official **Ollama** app (API only, `http://ollama_ollama_1:11434`)
- **App version:** store-versioned (`1.0.0`); the pinned upstream release is `2026.10.01.1`

## What it covers

| Need | Where |
|---|---|
| Model loaded / running now, GPU share, expiry | Dashboard, Memory page (`/api/ps`) |
| Unload (or load) a model | model menu, bulk unload |
| Installed models with details | Models: family, size, quant, context length, capabilities, downloaded, last used, load count; link to ollama.com or Hugging Face |
| Pull from the Ollama library | Discover (search) or Downloads (type a name) |
| Pull from Hugging Face | Discover → Hugging Face, or type `hf.co/<user>/<repo>:<quant>` |
| Per-model "update available" | **not available** (no candidate UI has it; re-pull a tag to update it) |

Extras: background download queue with progress/ETA, usage history, unused-model and duplicate-quant clean-up, model tests, blacklist, Ollama release check.

## First start: the app's own login

You sign in twice: Umbrel first, then the app (`admin`). The first admin password is printed **once** in the app's logs on first start:

```
Initial admin account created
  username: admin
  password: <24 random characters>
```

Read it from the app's logs (Umbrel dashboard: right-click the app → Troubleshoot, or on the box `sudo docker logs csikosjanos-ollama-model-manager_server_1`), sign in, and change it under **Settings**. Lost it:

```bash
# on the box
sudo docker exec csikosjanos-ollama-model-manager_server_1 /ollama-model-manager reset-password
```

## Environment variables

| Variable | Set by | Purpose |
|---|---|---|
| `OLLAMA_HOST` | compose | `$APP_OLLAMA_URL` from the Ollama app (fallback `http://ollama_ollama_1:11434`) |
| `DB_PATH` | compose | `/data/omm.db` |
| `TZ` | compose, override in `app-data/.env` | day boundaries for usage history (default `Etc/UTC`) |
| `HF_TOKEN` | *you, optional* | Hugging Face read token for private repos; set in `app-data/.env`, never commit |
| `ALLOW_MODEL_DELETE` | upstream default `true` | set `false` to hide Delete |

## Remote access over Tailscale

Following the `+10000` convention used by the other apps in this store:

```bash
tailscale serve --bg --https=21435 localhost:11435
```

## Notes and limitations

- **No GPU, no docker.sock, no Ollama files.** Everything goes through the Ollama API. Missing as a result: the System page's live GPU graph, Discover's "fits in VRAM" marks, and the free-disk-space tile (upstream reads those from `nvidia-smi` and a mount of Ollama's models folder). Per-model VRAM still shows (from `/api/ps`).
- **Server settings** (context length, parallel requests, flash attention, KV cache) are Ollama env vars. The app's *Settings → Ollama settings* only suggests values; apply them in the Ollama app's compose (see homelab #16/#17).
- **Runs as `1000:1000`** so it owns `data/` (umbrelOS creates committed package dirs as `1000:1000`; the distroless image has no shell to chown).
- **Outbound calls:** ollama.com and huggingface.co (search, pulls via Ollama), api.github.com (release checks).
- **Young project** (first release 2026-09-23, single maintainer). Pinned by digest; bump deliberately.
