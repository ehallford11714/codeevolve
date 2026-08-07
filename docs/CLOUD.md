# Model tiers, SLM taxonomy guide & cloud backends

CodeEvolve **defaults to an SLM tier** that always guides taxonomy (clade labels/roles). Swap up for sharper evolutionary studies.

## Model tiers

```powershell
python -m codeevolve tiers
python -m codeevolve --model-tier slm --repo . analyze          # default
python -m codeevolve --model-tier standard --repo . analyze
python -m codeevolve --model-tier large --repo . analyze
python -m codeevolve --model-tier frontier --repo . analyze
python -m codeevolve --model-tier large --model gpt-4o --repo . analyze
```

| Tier | Local HF (default) | Cloud default | Use for |
|------|--------------------|---------------|---------|
| `slm` | Qwen2.5-0.5B | gpt-4o-mini | Taxonomy guide + fast sketches (**default**) |
| `standard` | Qwen2.5-1.5B | gpt-4o-mini | Sharper clade naming / report polish |
| `large` | Qwen2.5-7B | gpt-4o | Deeper evolutionary studies |
| `frontier` | Qwen2.5-14B | gpt-4o / Claude Opus | Highest-fidelity narratives |

Taxonomy guidance always runs (unless `--no-taxonomy-guide`). **Default path tries the real local SLM** (`Qwen/Qwen2.5-0.5B-Instruct`, on-demand download via `ensure_default_slm`). If HF/cloud is unavailable, a deterministic **`slm_heuristic`** guide still labels niches.

```powershell
pip install -e ".[hf]"                 # real default SLM
python -m codeevolve hardware --ensure-slm
# taxonomy MiniLM (default for semantic niches when installed):
# pip install -e ".[semantic]"; python -m codeevolve hardware --ensure-embed
# optional tree-sitter symbols:
# pip install -e ".[treesitter]"
```

See [SEMANTIC.md](SEMANTIC.md) for MiniLM / Chroma / Pinecone taxonomy construction.


## Backend selection

```powershell
python -m codeevolve hardware --ensure-hf
python -m codeevolve --repo . analyze --llm auto
python -m codeevolve --repo . analyze --llm hf-qwen
python -m codeevolve --repo . analyze --llm openai
python -m codeevolve --repo . analyze --llm anthropic
python -m codeevolve --repo . analyze --llm heuristic
```

## Environment variables

| Variable | Purpose |
|----------|---------|
| `CODEEVOLVE_MODEL_TIER` | `slm` (default) \| `standard` \| `large` \| `frontier` |
| `CODEEVOLVE_HF_MODEL` | Override local model id |
| `CODEEVOLVE_LLM_MODEL` | Override cloud chat model |
| `CODEEVOLVE_LLM_API_KEY` / `OPENAI_API_KEY` | OpenAI-compatible |
| `CODEEVOLVE_LLM_BASE_URL` | OpenAI-compatible base URL |
| `ANTHROPIC_API_KEY` | Anthropic |
| `CODEEVOLVE_SKIP_HF` | `1` → skip local HF (use cloud or slm_heuristic) |
| `CODEEVOLVE_TAXONOMY_HEURISTIC` | `1` → force deterministic taxonomy guide |
| `CODEEVOLVE_HF_DOWNLOAD` | `1` → allow tokenizer prefetch |
| `GITHUB_TOKEN` / `GH_TOKEN` | Issues/PR selection pressure |
