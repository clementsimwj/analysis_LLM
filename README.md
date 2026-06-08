# Firebase Analytics Insights Pipeline

A configurable Python pipeline for parsing Firebase Analytics CSV exports and
generating model-based insights. The parser model and insight model are chosen
independently in `config.yaml`, while API keys stay in `.env`.

## Project Structure

```text
firebase_analytics/
├── analytics.py           # main entry point
├── app_config.py          # config.yaml and .env loading helpers
├── config.yaml            # provider/model settings
├── csv_parser.py          # splits CSV exports into named sections
├── insights.py            # section analysis and final report generation
├── requirements.txt
└── providers/
    ├── __init__.py        # provider factory
    ├── base.py            # provider interface
    ├── local.py           # local GGUF models via llama-cpp-python
    ├── anthropic.py       # Anthropic Claude API
    ├── openai.py          # OpenAI and OpenAI-compatible APIs
    ├── gemini.py          # Google Gemini API
    └── groq.py            # Groq via OpenAI-compatible API
```

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Install only the provider packages you need if you prefer a smaller environment:

```bash
pip install pyyaml
pip install llama-cpp-python huggingface-hub   # local
pip install anthropic                          # anthropic
pip install openai                             # openai or groq
pip install google-genai                       # gemini
```

## Secrets

Create a `.env` file in the project root. It is loaded automatically by
`analytics.py` before providers are created.

```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
GROQ_API_KEY=gsk_...
```

You can start from `.env.example`. The top-level `.gitignore` excludes `.env`.
If you use a different variable name, set `api_key_env` in `config.yaml`.
Gemini also accepts the older `GOOGLEGEMINI_API_KEY` alias for compatibility.

## Configuration

All provider and model switching happens in `config.yaml`.

```yaml
parser:
  provider: local
  model: "./models/Llama-3.2-3B-Instruct-Q4_K_M.gguf"
  max_tokens: 15
  temperature: 0.0
  n_ctx: 2048

insight:
  provider: groq
  model: llama-3.3-70b-versatile   # optional; defaults per provider
  api_key_env: GROQ_API_KEY        # optional; defaults per provider
  section_max_tokens: 200
  max_tokens: 800
  temperature: 0.1
  request_delay_seconds: 0
  max_retries: 3
  retry_base_delay_seconds: 30
```

`parser` is used only to name unnamed CSV sections, so a small local model is
usually enough. `insight` analyzes each section and writes the final report, so
use the stronger or cheaper service you prefer there.

Common fields:

| Field | Applies to | Description |
| --- | --- | --- |
| `provider` | all | `local`, `anthropic`, `openai`, `gemini`, or `groq` |
| `model` | all | Optional for cloud providers; API model name or local GGUF path |
| `temperature` | all | Sampling temperature |
| `max_tokens` | parser, insight | Parser title length or final report length |
| `section_max_tokens` | insight | Per-section analysis length |
| `api_key_env` | API providers | Name of the env var containing the API key |
| `base_url` | anthropic, openai, groq | Optional API/proxy endpoint override |
| `request_delay_seconds` | insight | Pause between insight calls to stay under RPM limits |
| `max_retries` | insight | Number of retries after rate-limit or transient API errors |
| `retry_base_delay_seconds` | insight | Fallback retry delay when the API does not provide one |
| `n_ctx`, `n_gpu_layers`, `n_batch`, `n_threads` | local | llama-cpp-python runtime settings |

## Provider Defaults

For cloud providers, the app has defaults for model, API key variable, and base
URL where needed. In the simplest case, set `provider` and add the matching key
to `.env`.

| Provider | Required `.env` key | Python package | Default model | Optional fields |
| --- | --- | --- | --- | --- |
| `groq` | `GROQ_API_KEY` | `openai` | `llama-3.3-70b-versatile` | `model`, `api_key_env`, `base_url` |
| `openai` | `OPENAI_API_KEY` | `openai` | `gpt-4o-mini` | `model`, `api_key_env`, `base_url` |
| `anthropic` | `ANTHROPIC_API_KEY` | `anthropic` | `claude-sonnet-4-20250514` | `model`, `api_key_env`, `base_url` |
| `gemini` | `GEMINI_API_KEY` | `google-genai` | `gemini-2.5-flash` | `model`, `api_key_env` |
| `local` | none | `llama-cpp-python` | `./models/Llama-3.2-3B-Instruct-Q4_K_M.gguf` | `model`, `n_ctx`, `n_gpu_layers`, `n_batch`, `n_threads` |

## Provider Examples

Local model:

```yaml
insight:
  provider: local
  model: "./models/Mistral-7B-Instruct-v0.3-Q4_K_M.gguf"
  section_max_tokens: 200
  max_tokens: 800
  temperature: 0.1
  n_ctx: 4096
  n_gpu_layers: -1
```

Anthropic:

```yaml
insight:
  provider: anthropic
  model: claude-sonnet-4-20250514
  api_key_env: ANTHROPIC_API_KEY
  max_tokens: 800
  temperature: 0.1
```

OpenAI:

```yaml
insight:
  provider: openai
  model: gpt-4o-mini
  api_key_env: OPENAI_API_KEY
  max_tokens: 800
  temperature: 0.1
```

OpenAI-compatible service:

```yaml
insight:
  provider: openai
  model: your-model-name
  api_key_env: YOUR_SERVICE_API_KEY
  base_url: https://your-service.example/v1
  max_tokens: 800
  temperature: 0.1
```

Gemini:

```yaml
insight:
  provider: gemini
  model: gemini-2.5-flash
  api_key_env: GEMINI_API_KEY
  max_tokens: 800
  temperature: 0.1
```

Groq:

```yaml
insight:
  provider: groq
  model: llama-3.3-70b-versatile
  api_key_env: GROQ_API_KEY
  max_tokens: 800
  temperature: 0.1
```

Groq is OpenAI-compatible under the hood. The provider uses
`https://api.groq.com/openai/v1` by default, so you only need `GROQ_API_KEY` and
a Groq model name.

Minimal Groq config:

```yaml
insight:
  provider: groq
```

## Downloading Local Models

Only needed when a role uses `provider: local`.

```bash
hf download bartowski/Llama-3.2-3B-Instruct-GGUF \
  --include "Llama-3.2-3B-Instruct-Q4_K_M.gguf" \
  --local-dir ./models

hf download bartowski/Mistral-7B-Instruct-v0.3-GGUF \
  --include "Mistral-7B-Instruct-v0.3-Q4_K_M.gguf" \
  --local-dir ./models
```

## Running

```bash
python3 analytics.py ./data/Firebase_overview_dashboard.csv
```

With another config file:

```bash
python3 analytics.py ./data/Events_Event_name.csv --config my_config.yaml
```

Pipeline steps:

1. Load `config.yaml` and `.env`.
2. Build the parser and insight providers from config.
3. Parse the CSV into sections.
4. Use the parser model to label unnamed sections.
5. Use the insight model for section analysis and the final report.

## Custom Models And APIs

### Custom OpenAI-Compatible API

Use this path for services that support OpenAI's chat completions format. You
do not need to add code.

1. Add the provider key to `.env`.

```bash
MY_PROVIDER_API_KEY=...
```

2. Configure `insight` with `provider: openai`, your model name, key name, and
   base URL.

```yaml
insight:
  provider: openai
  model: your-model-name
  api_key_env: MY_PROVIDER_API_KEY
  base_url: https://your-provider.example/v1
  max_tokens: 800
  temperature: 0.1
```

Groq is implemented this way internally, except it has a convenience
`provider: groq` alias with the base URL prefilled.

### Custom Local GGUF Model

Use this path for local models that work with `llama-cpp-python`.

1. Put the `.gguf` file under `models/`.
2. Point either `parser` or `insight` at that file.

```yaml
insight:
  provider: local
  model: "./models/Your-Model-Q4_K_M.gguf"
  max_tokens: 800
  temperature: 0.1
  n_ctx: 4096
  n_gpu_layers: -1
  n_batch: 256
  n_threads: 4
```

Useful local fields:

| Field | Meaning |
| --- | --- |
| `model` | Path to the `.gguf` file |
| `n_ctx` | Context window; increase for larger prompts if RAM allows |
| `n_gpu_layers` | `-1` tries to offload all layers to GPU |
| `n_batch` | Batch size for prompt processing |
| `n_threads` | CPU threads used by llama.cpp |

### Brand-New API Provider

Use this path only when the service is not OpenAI-compatible.

1. Create `providers/<name>.py`.
2. Subclass `BaseProvider` from `providers/base.py`.
3. Implement `complete()`, `unload()`, and `name`.
4. Register it in `providers/__init__.py`.
5. Add its key to `.env.example` and document the config in this README.

Minimal provider template:

```python
from .base import BaseProvider
from .env import get_api_key


class MyProvider(BaseProvider):
    def __init__(self, model: str, api_key_env: str = "MY_API_KEY"):
        self.model = model
        api_key = get_api_key(
            provider="myprovider",
            api_key_env=api_key_env,
            defaults=["MY_API_KEY"],
            example="...",
        )
        self._client = build_client_somehow(api_key)

    def complete(self, system: str, user: str, max_tokens: int, temperature: float) -> str:
        response = self._client.generate(
            model=self.model,
            system=system,
            prompt=user,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.text.strip()

    def unload(self):
        pass

    @property
    def name(self) -> str:
        return f"myprovider ({self.model})"
```

Register it:

```python
elif provider_type == "myprovider":
    from .myprovider import MyProvider
    return MyProvider(
        model=model,
        api_key_env=cfg.get("api_key_env", "MY_API_KEY"),
    )
```

Then configure it:

```yaml
insight:
  provider: myprovider
  model: my-model-name
  api_key_env: MY_API_KEY
```

The rest of the pipeline does not need to change as long as the provider follows
the `BaseProvider` interface.

## Troubleshooting

Missing API key:

```text
Set the matching key in .env, then make sure api_key_env in config.yaml uses
that exact variable name.
```

Gemini 429 quota error:

```text
The free tier can allow only a few requests per minute. Keep
request_delay_seconds at 13 or higher, or switch insight.provider to a paid
provider/key with a higher quota.
```

Local model fails to load:

```text
Check that the GGUF path exists, close memory-heavy apps, use a smaller model,
or switch that role to an API provider.
```

No sections found:

```text
The parser expects sections separated by blank lines, optional titles starting
with #, and a header row at the start of each section.
```
