# Qwen3-TTS (Web UI)

Alibaba Cloud's open-source [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) served
via [`cornball-ai/qwen3-tts-api`](https://github.com/cornball-ai/qwen3-tts-api) in
**Gradio Web UI** mode.

- **Image:** `ghcr.io/csikosjanos/qwen3-tts-api:cu124` (self-built from cornball-ai's `Dockerfile`, CUDA 12.4 base — runs on the box's 550/12.4 driver)
- **App id:** `csikosjanos-qwen3-tts`
- **Port:** 7860 (Gradio UI)
- **Model:** `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` (9 built-in speakers)

## ⚠️ VRAM — cannot run alongside Ollama
The 1.7B model uses **~8 GB VRAM = the whole card**. It **cannot** run at the same
time as Ollama or any other GPU app. Stop the other GPU app first, then start
this one. Voice cloning / voice design (12–16 GB) are **not usable** on 8 GB.

## First boot
Downloads the CustomVoice model (~7 GB) from Hugging Face into `${APP_DATA_DIR}/cache`
— first start is slow; subsequent starts are fast (cached).

## Build (how the image was made)
cornball-ai publishes **no** prebuilt image, so it's built from their `Dockerfile`
(already CUDA 12.4 — no edit needed, unlike Chatterbox):
```sh
git clone https://github.com/cornball-ai/qwen3-tts-api.git
cd qwen3-tts-api
docker build -f Dockerfile -t ghcr.io/csikosjanos/qwen3-tts-api:cu124 .
docker push ghcr.io/csikosjanos/qwen3-tts-api:cu124   # package made public
```

## Environment (key)
| Variable | Value | Purpose |
|---|---|---|
| `ENABLE_GRADIO` | `true` | Gradio UI instead of the API |
| `GRADIO_PORT` / `GRADIO_SERVER_NAME` | `7860` / `0.0.0.0` | UI port + bind for app_proxy |
| `MODEL_NAME` | `…1.7B-CustomVoice` | The one model that fits 8 GB |
| `LOCAL_FILES_ONLY` | `false` | Allow first-boot model download |
| `DEVICE` / `DTYPE` | `cuda:0` / `bfloat16` | GPU |

## Variants / limitations
- **API mode** (OpenAI-compatible, port 4123) can be a separate app — but it can't share the GPU with this one at the same time.
- Voice cloning/design need 12–16 GB VRAM → not usable here.
