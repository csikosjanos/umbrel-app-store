# Laya System One

Self-hosted [Laya](https://github.com/NandhaKishorM/laya) (Apache-2.0) behind a
**TypeSafe Jev-compatible** API: `POST /v1/systemone` with
`{state, model, questions}` → `{model, answers, usage}`. Question types `noul`,
`choice`, `score`, same as [docs.typesafe.ai/api](https://docs.typesafe.ai/api).

| | |
|---|---|
| Server | upstream `laya-serve` (FastAPI/uvicorn), unchanged |
| Image | `ghcr.io/csikosjanos/laya:v0.3.24-cu126`, built by `.github/workflows/build-laya.yml` from Laya `v0.3.24` @ `fa9a2a70` |
| Torch | 2.14.0 + CUDA 12.6 wheels (driver 550 / CUDA 12.4 via minor-version compat; fallback build: `cu124` + torch 2.6.0) |
| Models | `english` (ModernBERT-large, 421M, ~0.9 GB), `multilingual` (mmBERT-base, 322M, ~0.7 GB), `typed-decisions` (421M, ~0.9 GB) |
| Weights | Hugging Face `convaiinnovations/laya*`, pinned to the upstream-reviewed commits (`LAYA_REVISION=reviewed`) |
| Port | 8720 on the box (app_proxy) · `csikosjanos-laya_server_1:8000` inside Umbrel's network |
| Auth | `Authorization: Bearer <app password shown in the Umbrel dashboard>` |

## Resource limits (protect the GitHub runner)

| Limit | Value | Where |
|---|---|---|
| CPU | 4 cores (`cpus: 4.0`), torch threads 4 | compose |
| RAM | 6 GB hard (`mem_limit`, no extra swap) | compose |
| PIDs | 512 | compose |
| VRAM | ~1–1.5 GB per resident checkpoint, max 2 resident (estimate, unmeasured) | `LAYA_MAX_LOADED=2` |
| Concurrency | 8 requests in flight, then 503 | `LAYA_MAX_CONCURRENT` |
| Privileges | non-root (uid 10001), `cap_drop: ALL`, `no-new-privileges`, no docker.sock | compose |

GPU access comes from `permissions: [GPU]` in the manifest (umbreld adds the
NVIDIA device). If the GPU is missing or full, Laya falls back to CPU by itself;
`GET /health` (with the bearer key) shows `device` and `cpu_fallbacks`.

## Use it

```sh
KEY=<app password>
curl -s http://<box>:8720/v1/systemone \
  -H "authorization: Bearer $KEY" -H 'content-type: application/json' \
  -d '{"state":"Help! My payouts have been failing for 3 days.","model":"jev-latest",
       "questions":{"is_urgent":{"type":"noul","instructions":"Does this convey urgency?"},
                    "team":{"type":"choice","instructions":"Which team?",
                            "criteria":{"billing":"Payments","technical":"Bugs","sales":"Pricing"}}}}'
```

`model` may be any Jev name (auto-routes by language) or a Laya checkpoint
(`english`, `multilingual`, `typed-decisions`). The `X-Inference-Time-Ms`
response header gives server-side model time. `POST /v1/systemone/batch` takes
several states at once.

### As a CLIProxyAPI provider

In the CLIProxyAPI web console add an **OpenAI-compatibility** provider:

- Base URL: `http://csikosjanos-laya_server_1:8000/v1` (internal network, skips app_proxy)
- API key: this app's password
- Models: whatever names clients send (e.g. `laya`, `jev-latest`)

CLIProxyAPI forwards `/v1/systemone` unchanged to `<base URL>/v1/systemone`
(trailing `/v1` not doubled).

## Settings (`~/umbrel/app-data/csikosjanos-laya/.env`, then restart the app)

| Variable | Default | Meaning |
|---|---|---|
| `LAYA_DEVICE` | `cuda` | `cpu` keeps it off the GPU entirely |
| `LAYA_MODELS` | `english` | checkpoints preloaded at start (comma list) |
| `LAYA_MAX_LOADED` | `2` | checkpoints resident at once (bounds RAM/VRAM) |
| `LAYA_THREADS` | `4` | torch CPU threads (keep ≤ `cpus`) |
| `LAYA_MAX_CONCURRENT` | `8` | in-flight requests before 503 |
| `LAYA_JEV_STRICT` | `1` | `0` adds Laya extras (`routing`, `action`, `answer_confidence`) |
| `LAYA_REVISION` | `reviewed` | Hub revision for weights |
| `HF_HUB_OFFLINE` | `0` | `1` after first start = never contact Hugging Face |

## Notes

- No idle-unload: laya-serve keeps loaded checkpoints resident. Stop the app
  from the dashboard to free RAM/VRAM.
- Quality vs hosted Jev is not established here; compare on your own questions
  before relying on it (see homelab#18).
