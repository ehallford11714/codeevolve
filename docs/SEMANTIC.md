# Word2Vec + semantic taxonomy (Chroma / Pinecone)

CodeEvolve builds a **clearer taxonomy** from evolution text and per-repo vector niches.

## Pipeline

1. **Evolution corpus** — each commit → tokens from subject/body + path stems + churn/revert markers  
2. **Word2Vec** (Gensim when installed; co-occurrence fallback otherwise)  
   - neighbors for change terms  
   - clade label suggestions  
   - early→late term drift  
3. **Semantic niches** — embed file docs (path + snippet), upsert into a vector store, k-means niches  
4. **Clade refinement** — relabel structural clades when niche agreement ≥ 0.45

## Install

```powershell
pip install -e ".[semantic]"          # gensim + chromadb
# optional cloud index:
pip install -e ".[pinecone]"
```

## Backends

| Backend | When |
|---------|------|
| `memory` | Always available (tests / no deps) |
| `chromadb` | `pip install -e ".[chroma]"` or `CODEEVOLVE_USE_CHROMA=1` |
| `pinecone` | `PINECONE_API_KEY` + pre-created index (`CODEEVOLVE_PINECONE_INDEX`, cosine) |

```powershell
# auto: pinecone (if keyed) → chroma (if installed) → memory
python -m codeevolve --repo . analyze --vector-backend auto

$env:CODEEVOLVE_USE_CHROMA="1"
python -m codeevolve --repo . semantic-taxonomy

$env:PINECONE_API_KEY="..."
$env:CODEEVOLVE_PINECONE_INDEX="codeevolve"
python -m codeevolve --repo . analyze --vector-backend pinecone
```

Chroma persistence default: `~/.codeevolve/chroma` (`CODEEVOLVE_CHROMA_DIR`).

Skip gensim (force fallback): `CODEEVOLVE_SKIP_GENSIM=1`.

## CLI

```powershell
python -m codeevolve --repo . word2vec
python -m codeevolve --repo . semantic-taxonomy
python -m codeevolve --repo . taxonomy   # includes word2vec + semantic blocks
python -m codeevolve --repo . analyze --no-semantic
```

## Report fields

- `taxonomy.word2vec` — engine, neighbors, drift, clade_labels  
- `taxonomy.semantic` — backend, namespace, niches, clade_refinements  
- Clade `label` may be rewritten from Word2Vec/niche suggestions
