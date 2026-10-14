# YuE2

Full songs with vocals from style tags and lyrics, on your own GPU. Runs
[yue2.cpp](https://github.com/ServeurpersoCom/yue2.cpp) (C++/GGML port of
[M-A-P YuE2](https://github.com/multimodal-art-projection/YuE)) with quantized
GGUF weights from [Serveurperso/YuE2-GGUF](https://huggingface.co/Serveurperso/YuE2-GGUF).

- **Web UI** at the app URL: style + lyrics → song, the ABC score the model wrote, playback, downloads, covers.
- **Job API** on the same port, open without the Umbrel login (see Security).
- **Claude skill** `yue2-music` (in the homelab repo, `yue2/skill/`) wraps the API.

## Requirements

| Item | Value |
|---|---|
| GPU | NVIDIA, ≥ 6 GB VRAM (Q8_0). Built for compute 8.6 (RTX 30 series) |
| Driver | CUDA ≥ 12.4 capable |
| Disk | ~5.4 GB weights (Q8_0 + covers models) |

Upstream VRAM figures: a 65 s song in Q8_0 peaks at 5.8 GB (full context), 3.8 GB with `YUE2_MAX_SEQ=8192`.
Only one model part is in VRAM at a time; nothing stays on the GPU between requests.

## Configuration

Set in `~/umbrel/app-data/csikosjanos-yue2/.env`, then restart the app.

| Variable | Default | Meaning |
|---|---|---|
| `YUE2_QUANT` | `Q8_0` | Backbone: `Q8_0` (3.8 GB), `Q6_K`, `Q5_K_M`, `BF16` (7.2 GB) |
| `YUE2_COVERS` | `1` | Download + enable `/transcribe` and `/tokenize` (~1 GB) |
| `YUE2_MAX_SEQ` | empty | KV cache size; `8192` saves VRAM but limits song length |
| `YUE2_EXTRA_ARGS` | empty | Extra `yue-server` flags, e.g. `--keep-loaded` |
| `HF_TOKEN` | empty | Only if Hugging Face rate-limits the download |

LoRA adapters: drop files into `~/umbrel/app-data/csikosjanos-yue2/data/adapters/`, restart, pick them in the UI's Models menu.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/synth` | JSON request (`style`, `lyrics`, `abc`, `cot`, `duration`, `seed`, `output_format`…) → `{"id": "…"}` |
| GET | `/job?id=ID` | `{"status": "running\|done\|failed\|cancelled"}` |
| GET | `/job?id=ID&result=1` | `multipart/mixed`: per track a replay JSON (score + seeds + codes), the audio, the latents |
| POST | `/job?id=ID&cancel=1` | Cancel |
| POST | `/transcribe` | multipart `audio` (+ `melody_only`) → job; result `{"abc": "…"}` |
| GET | `/health`, `/props` | Health; version, models, default request |

Full reference: [ARCHITECTURE.md](https://github.com/ServeurpersoCom/yue2.cpp/blob/master/docs/ARCHITECTURE.md).

```bash
ID=$(curl -s -X POST http://umbrel.local:8087/synth -H 'Content-Type: application/json' \
  -d '{"style":"English, warm piano pop, female voice, 88 BPM","lyrics":"[Verse]\nNeon fades along the lane"}' | jq -r .id)
curl -s "http://umbrel.local:8087/job?id=$ID"            # poll until done
```

## Security

`yue-server` has no authentication. The API paths are whitelisted past the Umbrel
login so clients can call them, so anyone on the LAN/tailnet can generate songs and
fetch results. The UI at `/` stays behind the Umbrel login.

## Limitations

- Weights are **CC BY-NC 4.0**: non-commercial use only.
- One worker thread: jobs run one at a time (FIFO); finished results are kept in memory for the last 32 jobs and lost on restart.
- Shares the GPU with Ollama and other apps; a loaded Ollama model can cause out-of-memory errors.
- yue2.cpp is young (first release Sep 2026); the image pins a commit.
