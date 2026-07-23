# Chatterbox TTS

Self-hosted **text-to-speech with voice cloning** — Resemble AI's open-source
[Chatterbox](https://github.com/resemble-ai/chatterbox) model, served via
[`devnen/Chatterbox-TTS-Server`](https://github.com/devnen/Chatterbox-TTS-Server)
(Web UI + OpenAI-compatible API).

- **Image:** [`ghcr.io/devnen/chatterbox-tts-server:main-nvidia`](https://github.com/devnen/Chatterbox-TTS-Server/pkgs/container/chatterbox-tts-server) (CUDA 12.1)
- **App id:** `csikosjanos-chatterbox-tts`
- **Port:** 8004 (real Web UI + API)

## Resources

| | |
|---|---|
| **GPU** | Uses NVIDIA via `deploy.resources.reservations.devices`. Needs NVIDIA Container Toolkit on host. Shares VRAM with other GPU apps (e.g. Ollama). |
| **VRAM** | Not officially specified; 0.5B-param model (Turbo 350M). An 8 GB card handles it but watch contention. |
| **Disk** | 10 GB+ (deps already in image; model cache ~2 GB+ per model in `hf_cache`). |
| **First boot** | Slow — downloads the model from Hugging Face. |

## Variants

Switch the image tag in `docker-compose.yml` for other hardware:

| Hardware | Tag |
|---|---|
| NVIDIA RTX 20/30/40 (default) | `main-nvidia` |
| NVIDIA Blackwell / RTX 50 | `main-cu128` |
| AMD ROCm | `main-rocm` |
| **CPU only** (no GPU) | `main-cpu` — also remove the `deploy:` block |

## Model selection

Original / Turbo / Multilingual is chosen in the server's `config.yaml`
(`model.repo_id`). This build uses the server default (Original). To change it,
edit the config inside the app data dir once the server has generated it, or
mount your own `config.yaml`.

## Environment variables

| Variable | Purpose |
|---|---|
| `NVIDIA_VISIBLE_DEVICES=all` | Expose GPUs to the container |
| `NVIDIA_DRIVER_CAPABILITIES=compute,utility` | Required CUDA capabilities |
| `HF_HUB_ENABLE_HF_TRANSFER=1` | Faster model downloads |
| `TTS_BF16=auto` | ~40% faster on bf16-capable GPUs |

## Persistent data (`${APP_DATA_DIR}`)

`hf_cache/` (model cache), `voices/`, `reference_audio/`, `outputs/`, `logs/`.

## Caveat — GPU passthrough on Umbrel

Umbrel doesn't officially document GPU passthrough for community apps. This
compose uses the standard Docker Compose device reservation. If the GPU isn't
picked up, use the `main-cpu` tag and drop the `deploy:` block.
