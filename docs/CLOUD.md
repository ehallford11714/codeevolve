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

## Coding agent providers

The objective agent (`codeevolve agent`) resolves a chat endpoint via **auto** (default):

1. Strong GPU (≥8GB VRAM) → local `hf-qwen` ladder model  
2. Modest GPU / enough RAM → local `slm`  
3. Else first configured cloud: OpenAI → Anthropic → Grok → Kimi/K3 → OpenRouter  
4. Else heuristic scaffolds only  

```powershell
python -m codeevolve agent --list-providers
python -m codeevolve --repo . agent --provider openai --model gpt-4o
python -m codeevolve --repo . agent --provider anthropic --model claude-sonnet-4-20250514
python -m codeevolve --repo . agent --provider grok --model grok-3-mini
python -m codeevolve --repo . agent --provider kimik3 --model kimi-k2-0905-preview
python -m codeevolve --repo . agent --provider custom --base-url https://host/v1 --model my-model --api-key $env:KEY
python -m codeevolve --repo . agent --llm slm --model-tier standard
python -m codeevolve --repo . agent --llm hf-qwen   # GPU-sized Qwen
```

Copy [examples/models.json](../examples/models.json) to `.codeevolve/models.json` (repo or `~/.codeevolve/`) to set defaults without CLI flags.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `CODEEVOLVE_MODEL_TIER` | `slm` (default) \| `standard` \| `large` \| `frontier` |
| `CODEEVOLVE_HF_MODEL` | Override local model id |
| `CODEEVOLVE_LLM_MODEL` | Override cloud chat model |
| `CODEEVOLVE_LLM_API_KEY` / `OPENAI_API_KEY` | OpenAI-compatible |
| `CODEEVOLVE_LLM_BASE_URL` | OpenAI-compatible base URL |
| `ANTHROPIC_API_KEY` | Anthropic |
| `XAI_API_KEY` / `GROK_API_KEY` | xAI Grok |
| `MOONSHOT_API_KEY` / `KIMI_API_KEY` | Moonshot Kimi / Kimi K3 |
| `OPENROUTER_API_KEY` | OpenRouter |
| `CODEEVOLVE_AGENT_PROVIDER` | Default agent provider (`auto`, `grok`, …) |
| `CODEEVOLVE_AGENT_PREFER_LOCAL` | `1` → prefer SLM/HF even when cloud keys exist |
| `CODEEVOLVE_GROK_MODEL` / `CODEEVOLVE_KIMI_MODEL` / `CODEEVOLVE_KIMIK3_MODEL` | Provider model overrides |
| `CODEEVOLVE_SKIP_HF` | `1` → skip local HF (use cloud or slm_heuristic) |
| `CODEEVOLVE_TAXONOMY_HEURISTIC` | `1` → force deterministic taxonomy guide |
| `CODEEVOLVE_HF_DOWNLOAD` | `1` → allow tokenizer prefetch |
| `GITHUB_TOKEN` / `GH_TOKEN` | Issues/PR selection pressure |
