"""Semantic taxonomy via lightweight MiniLM embeddings + vector niches."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.embeddings import cosine, tokenize
from codeevolve.gitlog import CommitRecord, list_tracked_files
from codeevolve.models.taxonomy_embed import EmbedderInfo, embed_taxonomy_texts
from codeevolve.taxonomy.vector_store import VectorRecord, open_vector_store, repo_namespace
from codeevolve.taxonomy.word2vec import Word2VecReport, analyze_word2vec, path_tokens


@dataclass
class SemanticNiche:
    id: str
    label: str
    files: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    size: int = 0
    cohesion: float = 0.0
    mean_confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "files": list(self.files[:60]),
            "file_count": len(self.files),
            "terms": list(self.terms[:12]),
            "size": self.size,
            "cohesion": self.cohesion,
            "mean_confidence": self.mean_confidence,
        }


@dataclass
class SemanticTaxonomyReport:
    backend: str = "memory"
    namespace: str = ""
    niches: list[SemanticNiche] = field(default_factory=list)
    path_to_niche: dict[str, str] = field(default_factory=dict)
    path_confidence: dict[str, float] = field(default_factory=dict)
    word2vec: Word2VecReport | None = None
    clade_refinements: list[dict[str, Any]] = field(default_factory=list)
    embedder: dict[str, Any] = field(default_factory=dict)
    stored_vectors: int = 0
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "namespace": self.namespace,
            "embedder": dict(self.embedder),
            "niches": [n.to_dict() for n in self.niches],
            "path_to_niche": dict(list(self.path_to_niche.items())[:300]),
            "path_confidence": dict(list(self.path_confidence.items())[:300]),
            "word2vec": self.word2vec.to_dict() if self.word2vec else None,
            "clade_refinements": list(self.clade_refinements[:40]),
            "stored_vectors": self.stored_vectors,
            "summary": self.summary,
        }


def _file_document(repo: Path, path: str) -> str:
    """Richer doc for MiniLM: path roles + identifiers + comment lines."""
    from codeevolve.taxonomy.keywords import classify_path

    layer_bits = path_tokens(path)
    hit = classify_path(path)
    type_bits = " ".join(hit.type_path)
    idents: list[str] = []
    comments: list[str] = []
    fp = repo / path
    if fp.is_file():
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")[:2400]
            for ln in text.splitlines()[:120]:
                s = ln.strip()
                if s.startswith("#") or s.startswith("//") or s.startswith("*"):
                    comments.extend(tokenize(s)[:12])
            idents = tokenize(text)[:100]
        except OSError:
            pass
    # Natural-language-ish bag MiniLM can use
    return (
        f"file {path.replace('/', ' ').replace('_', ' ')} "
        f"type {type_bits} "
        f"modules {' '.join(layer_bits)} "
        f"symbols {' '.join(idents[:60])} "
        f"notes {' '.join(comments[:40])}"
    ).strip()


def _normalize(v: list[float]) -> list[float]:
    nrm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / nrm for x in v]


def _kmeans(
    vectors: list[list[float]],
    k: int,
    *,
    rounds: int = 15,
    seeds: list[list[float]] | None = None,
) -> tuple[list[int], list[list[float]]]:
    n = len(vectors)
    if n == 0:
        return [], []
    k = max(1, min(k, n))
    if seeds and len(seeds) >= k:
        centroids = [_normalize(s[:]) for s in seeds[:k]]
    else:
        centroids = [_normalize(vectors[i * n // k][:]) for i in range(k)]
    assign = [0] * n
    for _ in range(rounds):
        for i, v in enumerate(vectors):
            best, best_s = 0, -2.0
            for j, c in enumerate(centroids):
                s = cosine(v, c)
                if s > best_s:
                    best, best_s = j, s
            assign[i] = best
        new_c = [[0.0] * len(vectors[0]) for _ in range(k)]
        counts = [0] * k
        for i, v in enumerate(vectors):
            a = assign[i]
            counts[a] += 1
            for d, x in enumerate(v):
                new_c[a][d] += x
        for j in range(k):
            if counts[j] == 0:
                continue
            centroids[j] = _normalize([x / counts[j] for x in new_c[j]])
    return assign, centroids


def _soft_confidence(vectors: list[list[float]], assign: list[int], centroids: list[list[float]]) -> list[float]:
    out: list[float] = []
    for i, v in enumerate(vectors):
        sims = sorted((cosine(v, c) for c in centroids), reverse=True)
        if not sims:
            out.append(0.0)
            continue
        best = sims[0]
        second = sims[1] if len(sims) > 1 else 0.0
        # margin + absolute similarity
        out.append(round(max(0.0, min(1.0, 0.55 * best + 0.45 * (best - second + 0.2))), 4))
    return out


def _niche_label_from_embed(
    files: list[str],
    docs: dict[str, str],
    centroid: list[float],
    *,
    w2v_terms: list[str] | None = None,
) -> tuple[str, list[str]]:
    terms: Counter[str] = Counter()
    for f in files:
        terms.update(path_tokens(f))
        terms.update(tokenize(docs.get(f, ""))[:30])
    stop = {
        "churn_low",
        "churn_mid",
        "churn_high",
        "py",
        "js",
        "ts",
        "src",
        "lib",
        "test",
        "tests",
        "file",
        "modules",
        "symbols",
        "notes",
    }
    candidates = [t for t, _ in terms.most_common(24) if t not in stop and len(t) > 2][:12]
    if w2v_terms:
        for t in w2v_terms:
            if t not in candidates and t not in stop:
                candidates.append(t)
    if not candidates:
        return (files[0].split("/")[0] if files else "niche"), []

    # Rank candidate phrases by embedding similarity to niche centroid
    phrases = candidates[:10] + ["/".join(candidates[:2])] + ["/".join(candidates[:3])]
    vecs, _ = embed_taxonomy_texts(phrases)
    scored: list[tuple[str, float]] = []
    for p, v in zip(phrases, vecs):
        scored.append((p, cosine(centroid, v)))
    scored.sort(key=lambda x: -x[1])
    label = scored[0][0] if scored else "/".join(candidates[:3])
    return label[:80], candidates[:6]


def build_semantic_taxonomy(
    repo: Path | str,
    commits: list[CommitRecord],
    *,
    display: str | None = None,
    path_to_clade: dict[str, str] | None = None,
    clades: list[dict[str, Any]] | None = None,
    max_files: int = 400,
    max_niches: int = 10,
    backend: str | None = None,
    include_word2vec: bool = True,
) -> SemanticTaxonomyReport:
    root = Path(repo)
    hist = sorted({f for c in commits for f in c.files})
    tracked = list_tracked_files(root)
    paths = (hist or tracked)[:max_files]
    paths = [
        p
        for p in paths
        if Path(p).suffix.lower()
        in {".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java", ".rb", ".php", ".cs", ""}
        or "/" in p
    ][:max_files]
    if not paths:
        paths = (hist or tracked)[:max_files]

    docs = {p: _file_document(root, p) for p in paths}
    doc_list = [docs[p] for p in paths]
    vectors, emb_info = embed_taxonomy_texts(doc_list)
    dim = len(vectors[0]) if vectors else 64

    # Hybrid deepening: seed centroids from structural clade means when available
    seeds: list[list[float]] | None = None
    if path_to_clade and vectors:
        by_clade_idx: dict[str, list[int]] = defaultdict(list)
        for i, p in enumerate(paths):
            cid = path_to_clade.get(p)
            if cid:
                by_clade_idx[cid].append(i)
        seeds = []
        for idxs in sorted(by_clade_idx.values(), key=len, reverse=True)[:max_niches]:
            acc = [0.0] * dim
            for i in idxs:
                for d, x in enumerate(vectors[i]):
                    acc[d] += x
            seeds.append(_normalize([x / max(1, len(idxs)) for x in acc]))

    ns = repo_namespace(root, display)
    store = open_vector_store(ns, dimension=dim, backend=backend)
    records = [
        VectorRecord(
            id=re.sub(r"[^a-zA-Z0-9_-]", "_", p)[:64],
            text=docs[p][:1200],
            vector=vectors[i],
            metadata={"path": p, "repo": ns, "embedder": emb_info.engine},
        )
        for i, p in enumerate(paths)
    ]
    stored = store.upsert(records)

    k = max(2, min(max_niches, max(2, int(math.sqrt(len(paths))) if paths else 2)))
    if seeds:
        k = max(k, min(max_niches, len(seeds)))
    assign, centroids = _kmeans(vectors, k, seeds=seeds)
    confidences = _soft_confidence(vectors, assign, centroids)

    groups: dict[int, list[int]] = defaultdict(list)
    for i, a in enumerate(assign):
        groups[a].append(i)

    w2v = None
    clade_files = None
    if include_word2vec:
        if clades:
            clade_files = {c["id"]: list(c.get("files") or []) for c in clades}
        elif path_to_clade:
            clade_files = defaultdict(list)
            for p, cid in path_to_clade.items():
                clade_files[cid].append(p)
            clade_files = dict(clade_files)
        w2v = analyze_word2vec(commits, path_to_clade=path_to_clade, clade_files=clade_files)

    niches: list[SemanticNiche] = []
    path_to_niche: dict[str, str] = {}
    path_confidence: dict[str, float] = {}
    for gi, idxs in sorted(groups.items(), key=lambda x: -len(x[1])):
        files = [paths[i] for i in idxs]
        centroid = centroids[gi] if gi < len(centroids) else vectors[idxs[0]]
        w2v_terms: list[str] = []
        if w2v and path_to_clade:
            votes = Counter(path_to_clade.get(f, "") for f in files)
            top_clade = votes.most_common(1)[0][0] if votes else ""
            lab = w2v.clade_labels.get(top_clade or "", "")
            if lab:
                w2v_terms = [t for t in re.split(r"[/|]", lab) if t]
        label, terms = _niche_label_from_embed(files, docs, centroid, w2v_terms=w2v_terms)
        sims = []
        sample = idxs[:12]
        for a in range(len(sample)):
            for b in range(a + 1, len(sample)):
                sims.append(cosine(vectors[sample[a]], vectors[sample[b]]))
        cohesion = sum(sims) / len(sims) if sims else 0.0
        mean_conf = sum(confidences[i] for i in idxs) / max(1, len(idxs))
        nid = f"niche_{len(niches):02d}"
        niches.append(
            SemanticNiche(
                id=nid,
                label=label,
                files=files,
                terms=terms,
                size=len(files),
                cohesion=round(cohesion, 4),
                mean_confidence=round(mean_conf, 4),
            )
        )
        for i in idxs:
            path_to_niche[paths[i]] = nid
            path_confidence[paths[i]] = confidences[i]

    refinements: list[dict[str, Any]] = []
    if path_to_clade:
        by_clade: dict[str, list[str]] = defaultdict(list)
        for p, cid in path_to_clade.items():
            by_clade[cid].append(p)
        for cid, files in by_clade.items():
            niche_votes = Counter(path_to_niche[f] for f in files if f in path_to_niche)
            top_niche = niche_votes.most_common(1)[0][0] if niche_votes else None
            niche_label = next((n.label for n in niches if n.id == top_niche), None)
            wlabel = w2v.clade_labels.get(cid) if w2v else None
            # Prefer embedding niche label; blend w2v when both present
            if niche_label and wlabel and wlabel.split("/")[0] not in niche_label:
                suggested = f"{niche_label}|{wlabel}"
            else:
                suggested = niche_label or wlabel or cid
            confs = [path_confidence[f] for f in files if f in path_confidence]
            refinements.append(
                {
                    "clade_id": cid,
                    "semantic_niche": top_niche,
                    "suggested_label": suggested,
                    "word2vec_label": wlabel,
                    "niche_label": niche_label,
                    "agreement": round(
                        (niche_votes.most_common(1)[0][1] / max(1, len(files))) if niche_votes else 0.0,
                        4,
                    ),
                    "mean_embed_confidence": round(sum(confs) / max(1, len(confs)), 4) if confs else 0.0,
                    "embedder": emb_info.engine,
                }
            )

    if niches and vectors:
        _ = store.query(vectors[0], top_k=3)

    return SemanticTaxonomyReport(
        backend=getattr(store, "name", "memory"),
        namespace=ns,
        niches=niches,
        path_to_niche=path_to_niche,
        path_confidence=path_confidence,
        word2vec=w2v,
        clade_refinements=refinements,
        embedder=emb_info.to_dict(),
        stored_vectors=stored,
        summary=(
            f"Semantic taxonomy via MiniLM-path[{emb_info.engine}:{emb_info.model_id}] "
            f"+ {getattr(store, 'name', 'memory')}[{ns}]: {len(niches)} niches, {stored} vectors"
            + (f"; {w2v.engine} word2vec" if w2v else "")
        ),
    )


def apply_semantic_labels_to_clades(clades: list[Any], semantic: SemanticTaxonomyReport) -> int:
    """Mutate clade.label when semantic refinement is confident."""
    by_id = {r["clade_id"]: r for r in semantic.clade_refinements}
    n = 0
    for c in clades:
        ref = by_id.get(c.id)
        if not ref:
            continue
        agreement = float(ref.get("agreement") or 0)
        embed_conf = float(ref.get("mean_embed_confidence") or 0)
        if agreement >= 0.4 and embed_conf >= 0.35 and ref.get("suggested_label"):
            c.role = c.role or f"semantic:{ref.get('embedder') or 'embed'}"
            if c.label != ref["suggested_label"]:
                c.label = str(ref["suggested_label"])[:80]
                n += 1
    return n
