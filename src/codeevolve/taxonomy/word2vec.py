"""Gensim Word2Vec (with fallback) over code-evolution corpora."""

from __future__ import annotations

import math
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.embeddings import cosine, tokenize
from codeevolve.gitlog import CommitRecord

_PATH_SPLIT = re.compile(r"[/\\._\-\s]+")


@dataclass
class Word2VecReport:
    engine: str = "none"
    vocab_size: int = 0
    vector_size: int = 0
    corpus_sentences: int = 0
    top_terms: list[dict[str, Any]] = field(default_factory=list)
    change_neighbors: list[dict[str, Any]] = field(default_factory=list)
    clade_labels: dict[str, str] = field(default_factory=dict)
    semantic_drift: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "vocab_size": self.vocab_size,
            "vector_size": self.vector_size,
            "corpus_sentences": self.corpus_sentences,
            "top_terms": list(self.top_terms[:40]),
            "change_neighbors": list(self.change_neighbors[:40]),
            "clade_labels": dict(list(self.clade_labels.items())[:40]),
            "semantic_drift": list(self.semantic_drift[:30]),
            "summary": self.summary,
        }


def path_tokens(path: str) -> list[str]:
    parts = [p for p in _PATH_SPLIT.split(path.replace("\\", "/")) if p]
    out: list[str] = []
    for p in parts:
        out.extend(tokenize(p))
        if p.lower() not in out:
            out.append(p.lower())
    return [t for t in out if len(t) > 1]


def build_evolution_corpus(commits: list[CommitRecord]) -> list[list[str]]:
    """One sentence per commit: subject tokens + path stems (+ ticket-ish tokens)."""
    sentences: list[list[str]] = []
    for c in sorted(commits, key=lambda x: x.timestamp):
        toks = tokenize(c.subject) + tokenize(c.body[:240])
        for f in c.files[:30]:
            toks.extend(path_tokens(f))
        # mark change intensity lightly
        churn = c.insertions + c.deletions
        if churn > 200:
            toks.append("churn_high")
        elif churn > 40:
            toks.append("churn_mid")
        else:
            toks.append("churn_low")
        if c.is_revert:
            toks.append("revert_event")
        # dedupe while preserving order
        seen: set[str] = set()
        sent = []
        for t in toks:
            if t not in seen:
                seen.add(t)
                sent.append(t)
        if len(sent) >= 2:
            sentences.append(sent)
    return sentences


class _FallbackW2V:
    """Co-occurrence PMI-ish vectors when gensim is unavailable."""

    def __init__(self, sentences: list[list[str]], *, dim: int = 64, window: int = 2) -> None:
        self.vector_size = dim
        co: dict[str, Counter[str]] = defaultdict(Counter)
        df: Counter[str] = Counter()
        for sent in sentences:
            uniq = list(dict.fromkeys(sent))
            for t in uniq:
                df[t] += 1
            for i, a in enumerate(sent):
                for b in sent[max(0, i - window) : i + window + 1]:
                    if a != b:
                        co[a][b] += 1
        vocab = [t for t, n in df.items() if n >= 2]
        self._vocab = set(vocab)
        self.wv: dict[str, list[float]] = {}
        # hash-project co-occurrence rows
        for term in vocab:
            vec = [0.0] * dim
            for other, w in co[term].most_common(40):
                h = abs(hash(other)) % dim
                vec[h] += float(w)
            nrm = math.sqrt(sum(v * v for v in vec)) or 1.0
            self.wv[term] = [v / nrm for v in vec]

    def __contains__(self, key: str) -> bool:
        return key in self.wv

    def most_similar(self, positive: list[str], topn: int = 8) -> list[tuple[str, float]]:
        seeds = [self.wv[p] for p in positive if p in self.wv]
        if not seeds:
            return []
        dim = len(seeds[0])
        q = [0.0] * dim
        for s in seeds:
            for i, x in enumerate(s):
                q[i] += x
        nrm = math.sqrt(sum(v * v for v in q)) or 1.0
        q = [v / nrm for v in q]
        scored = []
        skip = set(positive)
        for term, vec in self.wv.items():
            if term in skip:
                continue
            scored.append((term, cosine(q, vec)))
        scored.sort(key=lambda x: -x[1])
        return scored[:topn]


def _train_gensim(sentences: list[list[str]], *, vector_size: int = 64) -> Any | None:
    if os.environ.get("CODEEVOLVE_SKIP_GENSIM", "").lower() in {"1", "true", "yes"}:
        return None
    try:
        from gensim.models import Word2Vec
    except Exception:
        return None
    if len(sentences) < 3:
        return None
    try:
        model = Word2Vec(
            sentences=sentences,
            vector_size=vector_size,
            window=5,
            min_count=2,
            workers=1,
            sg=1,
            epochs=min(30, max(8, 80 // max(1, len(sentences) // 10))),
            seed=42,
        )
        return model
    except Exception:
        return None


def mean_vector(model: Any, tokens: list[str]) -> list[float] | None:
    vecs = []
    wv = model.wv if hasattr(model, "wv") and not isinstance(model.wv, dict) else model.wv
    for t in tokens:
        try:
            if t in wv:
                v = wv[t]
                vecs.append([float(x) for x in v])
        except Exception:
            continue
    if not vecs:
        return None
    dim = len(vecs[0])
    acc = [0.0] * dim
    for v in vecs:
        for i, x in enumerate(v):
            acc[i] += x
    n = float(len(vecs))
    return [x / n for x in acc]


def analyze_word2vec(
    commits: list[CommitRecord],
    *,
    path_to_clade: dict[str, str] | None = None,
    clade_files: dict[str, list[str]] | None = None,
    vector_size: int = 64,
) -> Word2VecReport:
    sentences = build_evolution_corpus(commits)
    if not sentences:
        return Word2VecReport(summary="Empty evolution corpus")

    model = _train_gensim(sentences, vector_size=vector_size)
    engine = "gensim"
    if model is None:
        model = _FallbackW2V(sentences, dim=vector_size)
        engine = "cooccurrence_fallback"

    # term frequency
    tf: Counter[str] = Counter()
    for s in sentences:
        tf.update(s)
    top_terms = [{"term": t, "count": n} for t, n in tf.most_common(40)]

    # neighbors for frequent path-ish / change terms
    seeds = [t for t, _ in tf.most_common(80) if t not in {"churn_low", "churn_mid", "churn_high"}][:12]
    neighbors: list[dict[str, Any]] = []
    wv = model.wv
    for seed in seeds:
        try:
            if seed not in wv:
                continue
            if engine == "gensim":
                sims = model.wv.most_similar(seed, topn=6)
            else:
                sims = model.most_similar([seed], topn=6)
            neighbors.append(
                {
                    "term": seed,
                    "neighbors": [{"term": t, "score": round(float(s), 4)} for t, s in sims],
                }
            )
        except Exception:
            continue

    # clade labels from nearest neighbors of file-path tokens
    clade_labels: dict[str, str] = {}
    if clade_files:
        for cid, files in clade_files.items():
            toks: list[str] = []
            for f in files[:40]:
                toks.extend(path_tokens(f))
            counts = Counter(toks)
            focus = [t for t, _ in counts.most_common(8) if t in wv]
            label_parts: list[str] = []
            for t in focus[:3]:
                label_parts.append(t)
                try:
                    if engine == "gensim":
                        sims = model.wv.most_similar(t, topn=2)
                    else:
                        sims = model.most_similar([t], topn=2)
                    for nt, _ in sims:
                        if nt not in label_parts and nt not in {"churn_low", "churn_mid", "churn_high"}:
                            label_parts.append(nt)
                            break
                except Exception:
                    pass
            if label_parts:
                clade_labels[cid] = "/".join(label_parts[:4])

    # semantic drift: early vs late mean vectors for top terms
    ordered = sorted(commits, key=lambda c: c.timestamp)
    mid = max(1, len(ordered) // 2)
    early_sents = build_evolution_corpus(ordered[:mid])
    late_sents = build_evolution_corpus(ordered[mid:])
    early_tf = Counter(t for s in early_sents for t in s)
    late_tf = Counter(t for s in late_sents for t in s)
    drift_rows: list[dict[str, Any]] = []
    for term, _ in tf.most_common(50):
        if term not in wv:
            continue
        # presence shift
        e = early_tf.get(term, 0) / max(1, sum(early_tf.values()))
        l = late_tf.get(term, 0) / max(1, sum(late_tf.values()))
        shift = l - e
        if abs(shift) < 0.002:
            continue
        drift_rows.append(
            {
                "term": term,
                "early_share": round(e, 5),
                "late_share": round(l, 5),
                "shift": round(shift, 5),
            }
        )
    drift_rows.sort(key=lambda r: -abs(r["shift"]))

    vocab_size = len(wv) if hasattr(wv, "__len__") else len(getattr(model, "wv", {}))
    return Word2VecReport(
        engine=engine,
        vocab_size=int(vocab_size),
        vector_size=vector_size,
        corpus_sentences=len(sentences),
        top_terms=top_terms,
        change_neighbors=neighbors,
        clade_labels=clade_labels,
        semantic_drift=drift_rows[:30],
        summary=(
            f"Word2Vec/{engine}: {vocab_size} terms from {len(sentences)} commit sentences; "
            f"{len(clade_labels)} clade labels; {len(drift_rows)} drifting terms"
        ),
    )


def embed_tokens_w2v(model: Any, tokens: list[str], *, dim: int = 64) -> list[float]:
    v = mean_vector(model, tokens)
    if v is not None:
        return v
    # fallback hash
    from codeevolve.embeddings import embed_text

    return embed_text(" ".join(tokens), dim=dim)
