# Word2Vec + MiniLM semantic taxonomy (Chroma / Pinecone)

CodeEvolve builds a **clearer taxonomy** from evolution text and per-repo vector niches, deepened with a **lightweight open-source embedding model**.

## Default taxonomy embedder

| Model | Role |
|-------|------|
| `sentence-transformers/all-MiniLM-L6-v2` | **Default** — ~80MB, strong local quality/size |
| `sentence-transformers/paraphrase-MiniLM-L3-v2` | Lighter — set `CODEEVOLVE_EMBED_LIGHT=1` |

Override: `CODEEVOLVE_EMBED_MODEL=<hf-id>`.

Taxonomy construction **prefers MiniLM automatically** (batch encode). Falls back to hashing-trick vectors when deps/env skip embeds.

```powershell
pip install -e ".[semantic]"          # MiniLM + gensim + chromadb
python -m codeevolve hardware --ensure-embed
```

| Env | Effect |
|-----|--------|
| `CODEEVOLVE_SKIP_EMBED=1` | Force hash fallback |
| `CODEEVOLVE_SKIP_HF=1` | Also skips MiniLM unless `CODEEVOLVE_FORCE_EMBED=1` |
| `CODEEVOLVE_EMBED_NO_DOWNLOAD=1` | Don’t fetch weights |
| `CODEEVOLVE_EMBED_LIGHT=1` | Use MiniLM-L3 |

## Pipeline (deepened)

1. **Evolution corpus** → Word2Vec neighbors / drift / clade hints  
2. **MiniLM file docs** — path + symbols + comment tokens (batch encoded)  
3. **Hybrid niches** — k-means seeded from structural clade centroids  
4. **Soft confidence** — assignment margin per file  
5. **Label ranking** — candidate niche phrases re-embedded and scored vs centroid  
6. **Vector store** — memory / Chroma / Pinecone per-repo namespace  
7. **Clade refinement** — relabel when niche agreement + embed confidence are high  

## Install / backends

```powershell
pip install -e ".[semantic]"          # embed + gensim + chromadb
pip install -e ".[pinecone]"          # optional cloud index
```

| Backend | When |
|---------|------|
| `memory` | Always available |
| `chromadb` | installed or `CODEEVOLVE_USE_CHROMA=1` |
| `pinecone` | `PINECONE_API_KEY` + index |

```powershell
python -m codeevolve --repo . analyze --vector-backend auto
python -m codeevolve --repo . word2vec
python -m codeevolve --repo . semantic-taxonomy
python -m codeevolve --repo . analyze --no-semantic
```

Chroma dir: `~/.codeevolve/chroma` (`CODEEVOLVE_CHROMA_DIR`).  
Skip gensim: `CODEEVOLVE_SKIP_GENSIM=1`.

## Report fields

- `taxonomy.semantic.embedder` — model id, engine (`sentence_transformers` \| `hash_fallback`), dim  
- `taxonomy.semantic.niches[].mean_confidence` / `cohesion`  
- `taxonomy.semantic.path_confidence`  
- `taxonomy.word2vec` — neighbors, drift, clade_labels  
- Clade `label` / `role` may be rewritten from MiniLM niche + Word2Vec blend
