"""Hierarchy taxonomy + co-change clade clustering + delta allocation."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.embeddings import cosine, embed_text
from codeevolve.gitlog import CommitRecord, list_tracked_files

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "layer": self.layer,
            "role": self.role,
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
        }


def _cochange_clusters(commits: list[CommitRecord], paths: list[str], max_clades: int = 12) -> dict[str, str]:
    """Assign paths to clade ids via top-dir + co-change reinforcement + embedding merge."""
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

    # Seed by top directory
    by_dir: dict[str, list[str]] = defaultdict(list)
    for p in paths:
        by_dir[_top_dir(p)].append(p)

    # Merge small dirs that co-change heavily into larger ones using embeddings of path sets
    dir_keys = sorted(by_dir.keys(), key=lambda d: -len(by_dir[d]))
    mapping: dict[str, str] = {}
    clade_dirs: list[str] = []
    for d in dir_keys:
        if len(clade_dirs) >= max_clades:
            # attach to most similar existing
            emb = embed_text(d + " " + " ".join(by_dir[d][:20]), for_taxonomy=True)
            best, best_s = clade_dirs[0], -1.0
            for cd in clade_dirs:
                s = cosine(emb, embed_text(cd + " " + " ".join(by_dir[cd][:20]), for_taxonomy=True))
                if s > best_s:
                    best, best_s = cd, s
            for p in by_dir[d]:
                mapping[p] = best
        else:
            clade_dirs.append(d)
            for p in by_dir[d]:
                mapping[p] = d

    # Reinforce: if file co-changes more with another clade, reassign
    for p in list(mapping.keys()):
        votes: dict[str, int] = defaultdict(int)
        for other, w in co[p].items():
            if other in mapping:
                votes[mapping[other]] += w
        if votes:
            winner = max(votes, key=votes.get)  # type: ignore[arg-type]
            if votes[winner] >= 3 and votes[winner] > touches[p] * 0.3:
                mapping[p] = winner
    return mapping


def build_taxonomy(
    repo: Path | str,
    commits: list[CommitRecord],
    *,
    max_files: int = 2000,
    model_tier: str | None = "slm",
    model_override: str | None = None,
    guide: bool = True,
    include_semantic: bool = True,
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

    path_to_seed = _cochange_clusters(commits, paths)
    # Build clades
    groups: dict[str, list[str]] = defaultdict(list)
    for p, seed in path_to_seed.items():
        groups[seed].append(p)

    churn_by_file: dict[str, int] = defaultdict(int)
    touch_by_file: dict[str, int] = defaultdict(int)
    for c in commits:
        ch = c.insertions + c.deletions
        share = ch / max(1, len(c.files))
        for f in c.files:
            touch_by_file[f] += 1
            churn_by_file[f] += int(share)

    clades: list[Clade] = []
    path_to_clade: dict[str, str] = {}
    for i, (seed, files) in enumerate(sorted(groups.items(), key=lambda x: -len(x[1]))):
        cid = f"clade_{i:02d}"
        layer_counts: dict[str, int] = defaultdict(int)
        for f in files:
            layer_counts[_layer(f)] += 1
        dominant = max(layer_counts, key=layer_counts.get) if layer_counts else "other"  # type: ignore[arg-type]
        clade = Clade(
            id=cid,
            label=seed,
            layer=dominant,
            files=sorted(files),
            touch_count=sum(touch_by_file[f] for f in files),
            churn=sum(churn_by_file[f] for f in files),
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

    guidance_meta: dict[str, Any] = {"tier": model_tier or "slm", "guided": False}
    if guide:
        from codeevolve.models.guide import apply_guidance, guide_taxonomy

        # Default: always SLM-guide taxonomy (heuristic SLM if HF/cloud unavailable)
        g = guide_taxonomy(
            [c.to_dict() for c in clades],
            tier=model_tier or "slm",
            model_override=model_override,
        )
        guidance_meta = apply_guidance(clades, g)
        guidance_meta["guided"] = True

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
    )
