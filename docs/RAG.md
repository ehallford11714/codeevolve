# RAG + SLM taxonomy (0.12)

Taxonomy guidance is **SLM-first**, grounded in **retrieved code chunks** — not heuristic labels alone.

```
paths → chunk (≈700 chars, overlap) → MiniLM/hash embed → vector store
     → retrieve top chunks per clade → Qwen SLM JSON labels/roles/type_path
```

## Engine order

1. **`hf-slm-rag`** — local Qwen (default `Qwen/Qwen2.5-0.5B-Instruct`) + RAG evidence  
2. **`*-rag` cloud** — OpenAI/Anthropic with the same RAG payload (large/frontier, or if SLM missing)  
3. **`slm_heuristic`** — last resort only (still lightly uses RAG keywords)

Check `taxonomy.guidance.engine` / `taxonomy.guidance.rag_chunks_used` in report JSON.

## Commands

```powershell
# Default analyze: ensure SLM + chunk/RAG taxonomy
python -m codeevolve --repo . analyze --out report.json

# Force download SLM weights
$env:CODEEVOLVE_HF_DOWNLOAD = "1"
python -m codeevolve --repo . hardware --ensure-slm

# Skip RAG only (still tries SLM)
python -m codeevolve --repo . analyze --no-rag

# Force heuristic (CI / offline)
$env:CODEEVOLVE_TAXONOMY_HEURISTIC = "1"
```

## Vector backends

`--vector-backend memory|chromadb|pinecone` (same store family as semantic niches).  
RAG namespace is `ce-<repo>-rag`.

## Env knobs

| Env | Effect |
|-----|--------|
| `CODEEVOLVE_SKIP_HF=1` | Disable local SLM → cloud or heuristic |
| `CODEEVOLVE_TAXONOMY_HEURISTIC=1` | Force heuristic (tests/CI) |
| `CODEEVOLVE_HF_MODEL` | Override SLM id |
| `CODEEVOLVE_SKIP_EMBED=1` | Hash embeddings for chunks |
| `CODEEVOLVE_VECTOR_BACKEND` | memory / chromadb / pinecone |

## Output fields

- `taxonomy.rag` — chunk/file counts, backend, embedder  
- `taxonomy.guidance.engine` — prefer `hf-slm-rag`  
- `taxonomy.guidance.rag_chunks_used` — evidence volume  
- Clade `type_path` / `role` refined from retrieved excerpts  
