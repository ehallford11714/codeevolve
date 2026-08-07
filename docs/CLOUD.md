# Cloud & local LLM backends

CodeEvolve narratives (trend / repo report polish) use a **numeric-first planner**, then optionally an LLM.

## Backend selection

```powershell
python -m codeevolve hardware
python -m codeevolve hardware --ensure-hf
python -m codeevolve --repo . analyze --llm auto
python -m codeevolve --repo . analyze --llm hf-qwen
python -m codeevolve --repo . analyze --llm openai
python -m codeevolve --repo . analyze --llm anthropic
python -m codeevolve --repo . analyze --llm heuristic
```

| Backend | Requirements |
|---------|----------------|
| `heuristic` | None (always works) |
| `hf-qwen` | `pip install -e ".[hf]"` + enough RAM/VRAM |
| `openai` / OpenAI-compatible | `CODEEVOLVE_LLM_API_KEY` or `OPENAI_API_KEY` |
| `anthropic` | `ANTHROPIC_API_KEY` |
| `auto` | Hardware check → local Qwen if viable, else cloud if keyed, else heuristic |

## Environment variables

| Variable | Purpose |
|----------|---------|
| `CODEEVOLVE_LLM_BACKEND` | Default backend when `--llm` omitted from env-driven paths |
| `CODEEVOLVE_LLM_API_KEY` / `OPENAI_API_KEY` | Cloud chat completions |
| `CODEEVOLVE_LLM_BASE_URL` | OpenAI-compatible base (default `https://api.openai.com/v1`) |
| `CODEEVOLVE_LLM_MODEL` | Cloud model id (default `gpt-4o-mini`) |
| `ANTHROPIC_API_KEY` | Anthropic Messages API |
| `CODEEVOLVE_ANTHROPIC_MODEL` | Anthropic model override |
| `CODEEVOLVE_HF_MODEL` | Force HF model id |
| `CODEEVOLVE_SKIP_HF` | `1` → never load/download local models |
| `CODEEVOLVE_HF_DOWNLOAD` | `1` → allow tokenizer prefetch via `ensure_hf_qwen` |
| `CODEEVOLVE_RAM_GB` | Override detected RAM for tests |
| `GITHUB_TOKEN` / `GH_TOKEN` | Issues/PR selection-pressure API (higher rate limits) |

## Qwen ladder (hardware)

Same idea as iQueue: pick the largest `Qwen/Qwen2.5-*-Instruct` that fits RAM/VRAM, capped at 1.5B on CPU.
