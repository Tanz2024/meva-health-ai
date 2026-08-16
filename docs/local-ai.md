# MEVA Local AI

MEVA's AI layer runs entirely on your own machine using
[Ollama](https://ollama.com) — no API key, no cloud service, no paid
inference.

## Architecture

```text
User
 ↓
Local Ollama model        (src/meva/ai/ollama_client.py)
 ↓
MEVA tool-selection layer  (src/meva/ai/tools.py, src/meva/ai/agent.py)
 ↓
Existing MEVA MCP/FHIR functions
 ↓
Synthetic Synthea FHIR data
 ↓
Local model produces the final answer
```

The AI layer never touches FHIR files directly — it only calls the same
functions the MCP server (Stage 4) uses.

## Setup

1. Install Ollama: https://ollama.com/download
2. Pull a model that supports tool calling, e.g.:
   ```bash
   ollama pull qwen3:4b
   ```
3. Make sure Ollama is running (`ollama list` should work without errors).

## Configuration (optional)

| Env var | Default | Purpose |
|---|---|---|
| `MEVA_OLLAMA_URL` | `http://localhost:11434` | Ollama server address |
| `MEVA_MODEL` | `qwen3:4b` | Which local model to use |

No configuration is required for a normal local Ollama install.

## Usage

Interactive chat:
```bash
python3 examples/chat_local.py
```

One-off question:
```bash
python3 examples/ask_local.py "What allergies are recorded for patient <id>?"
```

Patient IDs must be given explicitly — ask `list_patients` (or run
`examples/ask_local.py "List the synthetic patients available in MEVA."`)
to find them.

## Safety

- All patients are synthetic (see `docs/synthetic-data.md`).
- The system prompt instructs the model to answer only from tool
  results, never diagnose or prescribe, and say so explicitly when
  evidence is missing.
- Tool calls are capped at 5 rounds per question to prevent infinite
  loops.
- Tool arguments and patient IDs are validated the same way as in the
  MCP server (Stage 4) — no arbitrary file access is possible.
