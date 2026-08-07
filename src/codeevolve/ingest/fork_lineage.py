"""Cross-path / optional cross-repo blob-hash lineage (copy-based reuse)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.gitlog import list_blobs_at


@dataclass
class ForkLineageReport:
    duplicate_blobs: list[dict[str, Any]] = field(default_factory=list)
    external_matches: list[dict[str, Any]] = field(default_factory=list)
    duplicate_ratio: float = 0.0
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "duplicate_blobs": list(self.duplicate_blobs[:40]),
            "external_matches": list(self.external_matches[:40]),
            "duplicate_ratio": self.duplicate_ratio,
            "summary": self.summary,
        }


def analyze_fork_lineage(
    repo: Path | str,
    *,
    peer_repos: list[Path | str] | None = None,
    max_blobs: int = 4000,
) -> ForkLineageReport:
    """Find identical blobs across paths (intra-repo) and optional peer repos."""
    blobs = list_blobs_at(repo, "HEAD", max_entries=max_blobs)
    by_sha: dict[str, list[str]] = defaultdict(list)
    for sha, path in blobs:
        # skip obvious binaries / lock noise optionally keep all
        by_sha[sha].append(path)

    dups = []
    dup_files = 0
    for sha, paths in by_sha.items():
        if len(paths) < 2:
            continue
        dup_files += len(paths)
        dups.append({"blob": sha[:12], "paths": paths[:12], "count": len(paths)})
    dups.sort(key=lambda d: -d["count"])
    ratio = dup_files / max(1, len(blobs))

    external: list[dict[str, Any]] = []
    for peer in peer_repos or []:
        peer_path = Path(peer)
        if not peer_path.exists():
            continue
        try:
            peer_blobs = list_blobs_at(peer_path, "HEAD", max_entries=max_blobs)
        except Exception:
            continue
        peer_set = {sha: path for sha, path in peer_blobs}
        local_set = {sha: paths[0] for sha, paths in by_sha.items()}
        shared = set(local_set) & set(peer_set)
        for sha in list(shared)[:50]:
            external.append(
                {
                    "blob": sha[:12],
                    "local_path": local_set[sha],
                    "peer_path": peer_set[sha],
                    "peer_repo": str(peer_path),
                    "kind": "external_gene_flow",
                }
            )

    return ForkLineageReport(
        duplicate_blobs=dups,
        external_matches=external,
        duplicate_ratio=round(ratio, 4),
        summary=(
            f"{len(dups)} duplicate blob groups ({ratio:.1%} files); "
            f"{len(external)} external matches"
        ),
    )
