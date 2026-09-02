# Promptfoo

Open-source evaluation framework for LLM prompts, models and agents. Pre-wired to the Ollama app on this box.

- **Upstream:** <https://github.com/promptfoo/promptfoo> · docs at <https://www.promptfoo.dev/docs/>
- **Image:** `ghcr.io/promptfoo/promptfoo:0.122.2` (pinned)
- **Port:** `8010` → container `3000` via Umbrel's `app_proxy`
- **Data:** `~/umbrel/app-data/csikosjanos-promptfoo/data` → `/home/promptfoo/.promptfoo` (SQLite eval history)
- **Depends on:** the official **Ollama** app
- **App version:** store-versioned (`1.0.1`); the pinned upstream release is promptfoo `0.122.2`

## What it is for

Define test cases once, run them across many models and prompts at the same time, and read the results as a side-by-side matrix.

The value is in the assertions, not the chat. A test case can require that output:

| Assertion kind | Example use |
|---|---|
| `contains` / `regex` | answer must mention a required term |
| `is-json` + schema | structured extraction actually parses |
| tool / function call | agent picks the right tool with valid arguments |
| `latency`, `cost` | stays inside a budget |
| `llm-rubric` | passes an LLM-as-judge rubric |
| `javascript` / `python` | arbitrary custom check |

Runs are repeatable, so you can tell whether a new model or a reworded prompt actually improved anything instead of guessing from one sample.

## Two ways to use it

**1. In the browser.** Open the app on port `8010` and use the built-in eval creator. Local Ollama models need no API key.

**2. From the promptfoo CLI on your laptop**, pushing results here for permanent history:

```bash
export PROMPTFOO_REMOTE_API_BASE_URL=http://umbrel.local:8010
export PROMPTFOO_REMOTE_APP_BASE_URL=http://umbrel.local:8010
npx promptfoo@latest eval
npx promptfoo@latest share
```

The CLI needs Node.js 22.22.0 or newer.

## Referring to Ollama models

Use promptfoo's Ollama provider IDs. The model string is exactly what `ollama list` shows, including the tag:

```yaml
providers:
  - ollama:chat:qwen3.8-9b:latest
  - ollama:chat:ornith:latest
  - ollama:chat:qwen3.6:35b

prompts:
  - 'Summarise this in two sentences: {{text}}'

tests:
  - vars:
      text: 'Your input here.'
    assert:
      - type: llm-rubric
        value: 'Is exactly two sentences and loses no key fact'
```

Model names pulled straight from Hugging Face contain slashes and extra colons, for example `hf.co/empero-ai/Qwen3.8-9B-GGUF:Q4_K_M`. Those can confuse provider-ID parsing. Give such a model a short alias first and use the alias everywhere:

```bash
curl -X POST http://umbrel.local:11434/api/copy \
  -d '{"source":"hf.co/empero-ai/Qwen3.8-9B-GGUF:Q4_K_M","destination":"qwen3.8-9b"}'
```

## Environment variables

| Variable | Set by | Purpose |
|---|---|---|
| `OLLAMA_BASE_URL` | compose | `http://ollama_ollama_1:11434` — the Ollama app over Umbrel's internal Docker network |
| `PROMPTFOO_DISABLE_TELEMETRY` | compose | `1` — no phoning home |
| `PROMPTFOO_DISABLE_UPDATE` | compose | `1` — image is pinned; updates come via the app store |
| `OPENAI_API_KEY` | *you, optional* | benchmark local models against OpenAI |
| `ANTHROPIC_API_KEY` | *you, optional* | benchmark local models against Claude |

Local-only evaluation needs **no** API key. To add cloud providers:

```bash
# on the box
echo 'OPENAI_API_KEY=sk-...' >> ~/umbrel/app-data/csikosjanos-promptfoo/.env
# then restart the app from the Umbrel dashboard
```

Never commit keys to this repo.

## Remote access over Tailscale

Following the `+10000` convention used by the other apps in this store:

```bash
tailscale serve --bg --https=18010 localhost:8010
```

Then reach it at `https://<host>.ts.net:18010`.

## Notes and limitations

- **No authentication.** `PROXY_AUTH_ADD` is `false` so the CLI and browser can both reach the API. Anyone who can reach port `8010` can read your eval history. Keep it on your LAN or tailnet.
- **Red teaming.** Promptfoo can probe models with jailbreak, prompt-injection and harmful-content attacks. Some of that functionality calls promptfoo's hosted service; purely local evaluation does not.
- **Not a GPU app.** Inference happens in the Ollama container. Promptfoo only orchestrates and scores.
- **Data directory ownership.** umbreld creates the app's data directory as `root`, but the image runs as uid `100`. A one-time `init_perms` service chowns it before the server starts; without it the server crash-loops on `SQLITE_CANTOPEN` (error 14).
- **Eval speed is Ollama's speed.** A large matrix against a 35B model takes a while — `OLLAMA_NUM_PARALLEL` on the Ollama app governs concurrency.
