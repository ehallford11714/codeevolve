"""Semantic taxonomy: embed files, store in Chroma/Pinecone, cluster niches."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.embeddings import cosine, embed_text, tokenize
from codeevolve.gitlog import CommitRecord, list_tracked_files
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "files": list(self.files[:60]),
            "file_count": len(self.files),
            "terms": list(self.terms[:12]),
            "size": self.size,
            "cohesion": self.cohesion,
        }


@dataclass
class SemanticTaxonomyReport:
    backend: str = "memory"
    namespace: str = ""
    niches: list[SemanticNiche] = field(default_factory=list)
    path_to_niche: dict[str, str] = field(default_factory=dict)
    word2vec: Word2VecReport | None = None
    clade_refinements: list[dict[str, Any]] = field(default_factory=list)
    stored_vectors: int = 0
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "namespace": self.namespace,
            "niches": [n.to_dict() for n in self.niches],
            "path_to_niche": dict(list(self.path_to_niche.items())[:300]),
            "word2vec": self.word2vec.to_dict() if self.word2vec else None,
            "clade_refinements": list(self.clade_refinements[:40]),
            "stored_vectors": self.stored_vectors,
            "summary": self.summary,
        }


def _file_document(repo: Path, path: str) -> str:
    layer_bits = path_tokens(path)
    snippet = ""
    fp = repo / path
    if fp.is_file():
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")[:1500]
            # keep identifiers + comments lightly
            snippet = " ".join(tokenize(text)[:80])
        except OSError:
            snippet = ""
    return f"{path} {' '.join(layer_bits)} {snippet}".strip()


def _kmeans(vectors: list[list[float]], k: int, *, rounds: int = 12) -> list[int]:
    n = len(vectors)
    if n == 0:
        return []
    k = max(1, min(k, n))
    # init: even spread
    centroids = [vectors[i * n // k][:] for i in range(k)]
    assign = [0] * n
    for _ in range(rounds):
        # assign
        for i, v in enumerate(vectors):
            best, best_s = 0, -2.0
            for j, c in enumerate(centroids):
                s = cosine(v, c)
                if s > best_s:
                    best, best_s = j, s
            assign[i] = best
        # update
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
            centroids[j] = [x / counts[j] for x in new_c[j]]
            nrm = math.sqrt(sum(x * x for x in centroids[j])) or 1.0
            centroids[j] = [x / nrm for x in centroids[j]]
    return assign


def _niche_label(files: list[str], docs: dict[str, str], w2v_labels: dict[str, str] | None = None) -> tuple[str, list[str]]:
    terms: Counter[str] = Counter()
    for f in files:
        terms.update(path_tokens(f))
        terms.update(tokenize(docs.get(f, ""))[:20])
    stop = {"churn_low", "churn_mid", "churn_high", "py", "js", "ts", "src", "lib", "test", "tests"}
    top = [t for t, _ in terms.most_common(16) if t not in stop and len(t) > 2][:6]
    label = "/".join(top[:3]) if top else (files[0].split("/")[0] if files else "niche")
    return label, top


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
    # prefer source-like
    paths = [
        p
        for p in paths
        if Path(p).suffix.lower() in {".py", ".js", ".ts", ".tsx", ".go", ".rs", ".java", ".rb", ".php", ".cs", ""}
        or "/" in p
    ][:max_files]
    if not paths:
        paths = (hist or tracked)[:max_files]

    docs = {p: _file_document(root, p) for p in paths}
    vectors = [embed_text(docs[p]) for p in paths]
    dim = len(vectors[0]) if vectors else 64

    ns = repo_namespace(root, display)
    store = open_vector_store(ns, dimension=dim, backend=backend)
    records = [
        VectorRecord(
            id=re.sub(r"[^a-zA-Z0-9_-]", "_", p)[:64],
            text=docs[p][:1200],
            vector=vectors[i],
            metadata={"path": p, "repo": ns},
        )
        for i, p in enumerate(paths)
    ]
    stored = store.upsert(records)

    k = max(2, min(max_niches, max(2, int(math.sqrt(len(paths))) if paths else 2)))
    assign = _kmeans(vectors, k)
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
    for gi, idxs in sorted(groups.items(), key=lambda x: -len(x[1])):
        files = [paths[i] for i in idxs]
        label, terms = _niche_label(files, docs)
        # optional w2v boost
        if w2v and w2v.clade_labels:
            # if majority structural clade has a w2v label, blend
            if path_to_clade:
                votes = Counter(path_to_clade.get(f, "") for f in files)
                top_clade = votes.most_common(1)[0][0] if votes else ""
                if top_clade and top_clade in w2v.clade_labels:
                    label = f"{w2v.clade_labels[top_clade]}|{label}"
        # cohesion = mean pairwise sim sample
        sims = []
        sample = idxs[:12]
        for a in range(len(sample)):
            for b in range(a + 1, len(sample)):
                sims.append(cosine(vectors[sample[a]], vectors[sample[b]]))
        cohesion = sum(sims) / len(sims) if sims else 0.0
        nid = f"niche_{len(niches):02d}"
        niche = SemanticNiche(
            id=nid,
            label=label,
            files=files,
            terms=terms,
            size=len(files),
            cohesion=round(cohesion, 4),
        )
        niches.append(niche)
        for f in files:
            path_to_niche[f] = nid

    # Refine structural clades with semantic niche majority + w2v labels
    refinements: list[dict[str, Any]] = []
    if path_to_clade:
        by_clade: dict[str, list[str]] = defaultdict(list)
        for p, cid in path_to_clade.items():
            by_clade[cid].append(p)
        for cid, files in by_clade.items():
            niche_votes = Counter(path_to_niche[f] for f in files if f in path_to_niche)
            top_niche = niche_votes.most_common(1)[0][0] if niche_votes else None
            niche_label = next((n.label for n in niches if n.id == top_niche), None)
            wlabel = (w2v.clade_labels.get(cid) if w2v else None)
            suggested = wlabel or niche_label or cid
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
                }
            )

    # nearest-neighbor sanity via store (centroid of largest niche)
    if niches and vectors:
        # already stored; query once to ensure backend works
        _ = store.query(vectors[0], top_k=3)

    return SemanticTaxonomyReport(
        backend=getattr(store, "name", "memory"),
        namespace=ns,
        niches=niches,
        path_to_niche=path_to_niche,
        word2vec=w2v,
        clade_refinements=refinements,
        stored_vectors=stored,
        summary=(
            f"Semantic taxonomy via {getattr(store, 'name', 'memory')}[{ns}]: "
            f"{len(niches)} niches, {stored} vectors"
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
        if float(ref.get("agreement") or 0) >= 0.45 and ref.get("suggested_label"):
            c.role = c.role or "semantic"
            # keep original seed in role note; replace label with clearer semantic name
            if c.label != ref["suggested_label"]:
                c.label = str(ref["suggested_label"])[:80]
                n += 1
    return n
