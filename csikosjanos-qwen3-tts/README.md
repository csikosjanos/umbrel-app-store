# Qwen3-TTS (API)

Alibaba Cloud's open-source [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) served
via [`cornball-ai/qwen3-tts-api`](https://github.com/cornball-ai/qwen3-tts-api) in
**API-only mode** — a FastAPI/uvicorn REST API with an **OpenAI-compatible**
speech endpoint. No web UI.

- **Image:** `ghcr.io/csikosjanos/qwen3-tts-api:cu124` (self-built from cornball-ai's `Dockerfile`, CUDA 12.4 base — runs on the box's 550/12.4 driver)
- **App id:** `csikosjanos-qwen3-tts`
- **Port:** 4123 (REST API, via app_proxy)
- **Model:** `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` (9 built-in speakers)

## ⚠️ VRAM — cannot run alongside Ollama
The 1.7B model uses **~8 GB VRAM = the whole card**. It **cannot** run at the same
time as Ollama or any other GPU app. Stop the other GPU app first, then start
this one. Voice cloning / voice design (12–16 GB) may **not** be usable on 8 GB.

## Endpoints
OpenAI-compatible. Base is the app_proxy address (port 4123 internally).

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | health (200 once uvicorn is up) |
| POST | `/v1/audio/speech` | TTS with a built-in speaker → WAV/MP3 |
| POST | `/v1/audio/speech/upload` | voice cloning (multipart) |
| POST | `/v1/audio/speech/design` | voice design from a text description |
| GET | `/v1/voices` | list the 9 built-in speakers |
| GET | `/docs` | Swagger UI |

Example (built-in voice → WAV):
```sh
curl -X POST http://<app-address>:4123/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input":"Hello from Qwen3 TTS.","voice":"Vivian","language":"English"}' \
  --output speech.wav
```

## First boot
Downloads the CustomVoice model (~7 GB) from Hugging Face into `${APP_DATA_DIR}/cache`
— first start is slow; subsequent starts are fast (cached). Health at `/health`.

## Build (how the image was made)
cornball-ai publishes **no** prebuilt image, so it's built from their `Dockerfile`
(already CUDA 12.4 — no edit needed):
```sh
git clone https://github.com/cornball-ai/qwen3-tts-api.git
cd qwen3-tts-api
docker build -f Dockerfile -t ghcr.io/csikosjanos/qwen3-tts-api:cu124 .
docker push ghcr.io/csikosjanos/qwen3-tts-api:cu124   # package made public
```

## Environment (key)
| Variable | Value | Purpose |
|---|---|---|
| `ENABLE_GRADIO` | `false` | run the FastAPI/uvicorn API (not Gradio) |
| `PORT` / `HOST` | `4123` / `0.0.0.0` | API port + bind for app_proxy |
| `MODEL_NAME` | `…1.7B-CustomVoice` | The one model that fits 8 GB |
| `LOCAL_FILES_ONLY` | `false` | Allow first-boot model download |
| `DEVICE` / `DTYPE` | `cuda:0` / `bfloat16` | GPU |

## Notes
- `USE_FLASH_ATTENTION` is `false` — flash_attn is not in the image.
- Gradio has been removed (was port 7860); this app is API-only on 4123.
- Voice cloning/design need 12–16 GB VRAM → may not be usable on an 8 GB card.
