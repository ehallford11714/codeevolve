"""Hierarchy taxonomy + co-change clade clustering + delta allocation."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.embeddings import cosine, embed_text
from codeevolve.gitlog import CommitRecord, list_tracked_files
from codeevolve.taxonomy.keywords import KeywordTaxonomyReport, analyze_keyword_taxonomy

_LANG = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".md": "docs",
    ".yml": "config",
    ".yaml": "config",
    ".toml": "config",
    ".json": "config",
}


def _layer(path: str) -> str:
    p = path.replace("\\", "/").lower()
    if re.search(r"(^|/)(tests?|spec)(/|$)|_test\.|\.test\.|\.spec\.", p):
        return "tests"
    if re.search(r"(^|/)(docs?|documentation)(/|$)|readme", p):
        return "docs"
    if re.search(r"(^|/)(config|settings|\.github|deploy|infra|ops)(/|$)", p):
        return "config"
    if re.search(r"(^|/)(utils?|helpers?|common|misc|shared)(/|$)", p):
        return "utility"
    if re.search(r"(^|/)(src|lib|pkg|app|core)(/|$)", p):
        return "core"
    return "other"


def _top_dir(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    return parts[0] if len(parts) > 1 else "(root)"


@dataclass
class Clade:
    id: str
    label: str
    layer: str
    files: list[str] = field(default_factory=list)
    touch_count: int = 0
    churn: int = 0
    role: str = ""
    code_type: str = ""
    type_path: list[str] = field(default_factory=list)
    type_mix: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "layer": self.layer,
            "role": self.role,
            "code_type": self.code_type,
            "type_path": list(self.type_path),
            "type_mix": dict(list(self.type_mix.items())[:12]),
            "files": list(self.files)[:80],
            "file_count": len(self.files),
            "touch_count": self.touch_count,
            "churn": self.churn,
        }


@dataclass
class AllocatedDelta:
    sha: str
    path: str
    clade_id: str
    lineage_id: str
    insertions: int
    deletions: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "sha": self.sha,
            "path": self.path,
            "clade_id": self.clade_id,
            "lineage_id": self.lineage_id,
            "insertions": self.insertions,
            "deletions": self.deletions,
        }


@dataclass
class TaxonomyReport:
    layers: dict[str, int]
    languages: dict[str, int]
    directories: dict[str, int]
    clades: list[Clade]
    path_to_clade: dict[str, str]
    allocations: list[AllocatedDelta]
    file_count: int
    guidance: dict[str, Any] = field(default_factory=dict)
    word2vec: dict[str, Any] | None = None
    semantic: dict[str, Any] | None = None
    keyword_taxonomy: KeywordTaxonomyReport | None = None
    rag: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "layers": dict(self.layers),
            "languages": dict(self.languages),
            "directories": dict(list(self.directories.items())[:40]),
            "clades": [c.to_dict() for c in self.clades],
            "path_to_clade": dict(list(self.path_to_clade.items())[:200]),
            "allocations": [a.to_dict() for a in self.allocations[:500]],
            "allocation_count": len(self.allocations),
            "file_count": self.file_count,
            "guidance": dict(self.guidance),
            "word2vec": self.word2vec,
            "semantic": self.semantic,
            "keyword_taxonomy": self.keyword_taxonomy.to_dict() if self.keyword_taxonomy else None,
            "rag": self.rag,
        }


def _type_family(seed: str) -> str:
    """Extract coarse type family from a breakout seed for reassignment guards."""
    if seed.startswith("type:"):
        body = seed.split("|", 1)[0].removeprefix("type:")
        return body.split("/", 1)[0] if body else ""
    return ""


def _cochange_clusters(
    commits: list[CommitRecord],
    paths: list[str],
    max_clades: int = 12,
    *,
    seed_by_path: dict[str, str] | None = None,
) -> dict[str, str]:
    """Assign paths via keyword/type seeds + top-dir + co-change + type-aware split."""
    path_set = set(paths)
    co: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    touches: dict[str, int] = defaultdict(int)
    for c in commits:
        files = [f for f in c.files if f in path_set][:40]
        for f in files:
            touches[f] += 1
        for i, a in enumerate(files):
            for b in files[i + 1 :]:
                co[a][b] += 1
                co[b][a] += 1

    # Seed by keyword type lineage (when available), else top directory
    by_seed: dict[str, list[str]] = defaultdict(list)
    for p in paths:
        seed = (seed_by_path or {}).get(p) or f"dir:{_top_dir(p)}"
        by_seed[seed].append(p)

    seed_keys = sorted(by_seed.keys(), key=lambda d: -len(by_seed[d]))
    mapping: dict[str, str] = {}
    clade_seeds: list[str] = []
    for d in seed_keys:
        if len(clade_seeds) >= max_clades:
            emb = embed_text(d + " " + " ".join(by_seed[d][:20]), for_taxonomy=True)
            best, best_s = clade_seeds[0], -1.0
            for cd in clade_seeds:
                # Prefer merging within the same type family when over cap
                if _type_family(d) and _type_family(d) == _type_family(cd):
                    s = cosine(emb, embed_text(cd + " " + " ".join(by_seed[cd][:20]), for_taxonomy=True)) + 0.15
                else:
                    s = cosine(emb, embed_text(cd + " " + " ".join(by_seed[cd][:20]), for_taxonomy=True))
                if s > best_s:
                    best, best_s = cd, s
            for p in by_seed[d]:
                mapping[p] = best
        else:
            clade_seeds.append(d)
            for p in by_seed[d]:
                mapping[p] = d

    # Co-change reinforce, but do not drag files across different type families
    for p in list(mapping.keys()):
        votes: dict[str, int] = defaultdict(int)
        my_fam = _type_family(mapping[p])
        for other, w in co[p].items():
            if other not in mapping:
                continue
            other_seed = mapping[other]
            ofam = _type_family(other_seed)
            if my_fam and ofam and my_fam != ofam:
                continue  # type-aware guard
            votes[other_seed] += w
        if votes:
            winner = max(votes, key=votes.get)  # type: ignore[arg-type]
            if votes[winner] >= 3 and votes[winner] > touches[p] * 0.3:
                mapping[p] = winner

    # Split oversized mixed seeds by 2-level type key when still under max_clades
    mapping = _split_mixed_type_clades(mapping, seed_by_path or {}, max_clades=max_clades)
    return mapping


def _split_mixed_type_clades(
    mapping: dict[str, str],
    seed_by_path: dict[str, str],
    *,
    max_clades: int,
    min_size: int = 8,
) -> dict[str, str]:
    """If a clade mixes multiple type families and is large, re-seed by type."""
    by: dict[str, list[str]] = defaultdict(list)
    for p, seed in mapping.items():
        by[seed].append(p)
    out = dict(mapping)
    n_clades = len(by)
    for seed, files in list(by.items()):
        if len(files) < min_size or n_clades >= max_clades:
            continue
        fams: dict[str, list[str]] = defaultdict(list)
        for p in files:
            raw = seed_by_path.get(p, seed)
            fam = _type_family(raw) or "unknown"
            # use 2-level type when available
            if raw.startswith("type:"):
                body = raw.split("|", 1)[0].removeprefix("type:")
                parts = body.split("/")
                key = "/".join(parts[:2]) if parts else fam
            else:
                key = fam
            fams[key].append(p)
        if len(fams) < 2:
            continue
        # Keep largest group on original seed; peel others into type seeds
        ranked = sorted(fams.items(), key=lambda x: -len(x[1]))
        for key, group in ranked[1:]:
            if n_clades >= max_clades or len(group) < 3:
                continue
            new_seed = f"type:{key}|split:{seed[:24]}"
            for p in group:
                out[p] = new_seed
            n_clades += 1
    return out


def build_taxonomy(
    repo: Path | str,
    commits: list[CommitRecord],
    *,
    max_files: int = 2000,
    model_tier: str | None = "slm",
    model_override: str | None = None,
    guide: bool = True,
    include_semantic: bool = True,
    include_rag: bool = True,
    vector_backend: str | None = None,
    display: str | None = None,
) -> TaxonomyReport:
    repo = Path(repo)
    tracked = list_tracked_files(repo)[:max_files]
    # Prefer files that appear in history
    hist_files = sorted({f for c in commits for f in c.files})
    paths = hist_files[:max_files] if hist_files else tracked

    layers: dict[str, int] = defaultdict(int)
    langs: dict[str, int] = defaultdict(int)
    dirs: dict[str, int] = defaultdict(int)
    for p in paths:
        layers[_layer(p)] += 1
        dirs[_top_dir(p)] += 1
        ext = Path(p).suffix.lower()
        langs[_LANG.get(ext, ext.lstrip(".") or "unknown")] += 1

    churn_by_file: dict[str, int] = defaultdict(int)
    touch_by_file: dict[str, int] = defaultdict(int)
    for c in commits:
        ch = c.insertions + c.deletions
        share = ch / max(1, len(c.files))
        for f in c.files:
            touch_by_file[f] += 1
            churn_by_file[f] += int(share)

    # Deep keyword classification guides breakout seeds
    path_extra: dict[str, list[str]] = defaultdict(list)
    for c in commits[:400]:
        subj_toks = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", f"{c.subject} {c.body}")[:20]
        for f in c.files:
            path_extra[f].extend(t.lower() for t in subj_toks)
    kw = analyze_keyword_taxonomy(paths, churn_by_path=dict(churn_by_file), path_extra=path_extra)

    path_to_seed = _cochange_clusters(commits, paths, seed_by_path=kw.breakout_seeds)
    groups: dict[str, list[str]] = defaultdict(list)
    for p, seed in path_to_seed.items():
        groups[seed].append(p)

    clades: list[Clade] = []
    path_to_clade: dict[str, str] = {}
    for i, (seed, files) in enumerate(sorted(groups.items(), key=lambda x: -len(x[1]))):
        cid = f"clade_{i:02d}"
        layer_counts: dict[str, int] = defaultdict(int)
        type_mix: Counter[str] = Counter()
        for f in files:
            layer_counts[_layer(f)] += 1
            hit = kw.path_types.get(f)
            if hit:
                type_mix[hit.type_key] += 1
        dominant = max(layer_counts, key=layer_counts.get) if layer_counts else "other"  # type: ignore[arg-type]
        top_type = type_mix.most_common(1)[0][0] if type_mix else ""
        type_path = top_type.split("/") if top_type else []
        # Prefer type-aware label when seed is typed
        label = seed
        if seed.startswith("type:") and top_type:
            label = top_type
        clade = Clade(
            id=cid,
            label=label,
            layer=dominant,
            files=sorted(files),
            touch_count=sum(touch_by_file[f] for f in files),
            churn=sum(churn_by_file[f] for f in files),
            code_type=top_type,
            type_path=type_path,
            type_mix=dict(type_mix.most_common(12)),
        )
        clades.append(clade)
        for f in files:
            path_to_clade[f] = cid

    allocations: list[AllocatedDelta] = []
    for c in commits:
        per = max(1, len(c.files))
        ins_share = c.insertions // per
        del_share = c.deletions // per
        for f in c.files:
            cid = path_to_clade.get(f, "clade_unknown")
            allocations.append(
                AllocatedDelta(
                    sha=c.sha,
                    path=f,
                    clade_id=cid,
                    lineage_id=f"lin:{f}",
                    insertions=ins_share,
                    deletions=del_share,
                )
            )

    # Chunk codebase → vector index → retrieve evidence for SLM taxonomy
    rag_meta: dict[str, Any] | None = None
    rag_evidence: dict[str, Any] | None = None
    if include_rag:
        from codeevolve.taxonomy.rag import build_rag_index, evidence_bundle

        rag_index = build_rag_index(
            repo,
            paths,
            display=display or str(repo),
            max_files=min(250, max_files),
            backend=vector_backend or "memory",
        )
        rag_meta = rag_index.to_dict()
        rag_evidence = evidence_bundle(rag_index, [c.to_dict() for c in clades])

    guidance_meta: dict[str, Any] = {"tier": model_tier or "slm", "guided": False}
    if guide:
        from codeevolve.models.guide import apply_guidance, guide_taxonomy

        # Default engine: real SLM + RAG chunks (heuristic only if SLM unavailable)
        g = guide_taxonomy(
            [c.to_dict() for c in clades],
            tier=model_tier or "slm",
            model_override=model_override,
            rag_evidence=rag_evidence,
            ensure_slm=True,
        )
        guidance_meta = apply_guidance(clades, g)
        guidance_meta["guided"] = True
        if rag_meta:
            guidance_meta["rag"] = rag_meta

    w2v_dict: dict[str, Any] | None = None
    sem_dict: dict[str, Any] | None = None
    if include_semantic:
        from codeevolve.taxonomy.semantic import apply_semantic_labels_to_clades, build_semantic_taxonomy

        sem = build_semantic_taxonomy(
            repo,
            commits,
            display=display or str(repo),
            path_to_clade=path_to_clade,
            clades=[c.to_dict() for c in clades],
            max_files=min(400, max_files),
            backend=vector_backend,
            include_word2vec=True,
        )
        n_relabel = apply_semantic_labels_to_clades(clades, sem)
        guidance_meta["semantic_relabeled"] = n_relabel
        guidance_meta["vector_backend"] = sem.backend
        w2v_dict = sem.word2vec.to_dict() if sem.word2vec else None
        sem_dict = sem.to_dict()

    guidance_meta["keyword_types"] = len(kw.type_counts)
    guidance_meta["keyword_summary"] = kw.summary

    return TaxonomyReport(
        layers=dict(sorted(layers.items(), key=lambda x: -x[1])),
        languages=dict(sorted(langs.items(), key=lambda x: -x[1])),
        directories=dict(sorted(dirs.items(), key=lambda x: -x[1])),
        clades=clades,
        path_to_clade=path_to_clade,
        allocations=allocations,
        file_count=len(paths),
        guidance=guidance_meta,
        word2vec=w2v_dict,
        semantic=sem_dict,
        keyword_taxonomy=kw,
        rag=rag_meta,
    )
