#!/usr/bin/env python3
"""Demo: real-repo dynamics + provenance deliberation.

Default target is pallets/click@8.4.0 (public tag). Prints trajectory summary,
top frames, a sample impulse/basin, and a path pack so you can see the loop.

Usage:
  python examples/demo_dynamics.py
  python examples/demo_dynamics.py --repo pallets/flask --ref 3.0.0
  python examples/demo_dynamics.py --max-commits 180 --out demo_pack.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow running from repo root without install
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("CODEEVOLVE_SKIP_HF", "1")
os.environ.setdefault("CODEEVOLVE_SKIP_EMBED", "1")
os.environ.setdefault("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
os.environ.setdefault("CODEEVOLVE_SKIP_GHSA", "1")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Demo CodeEvolve dynamics + provenance on a real tag")
    p.add_argument("--repo", default="pallets/click", help="GitHub owner/name")
    p.add_argument("--ref", default="8.4.0", help="Tag or rev to analyze")
    p.add_argument("--max-commits", type=int, default=200)
    p.add_argument("--path", default=None, help="Optional path for path_pack focus")
    p.add_argument("--out", default=None, help="Write deliberation pack JSON")
    args = p.parse_args(argv)

    from codeevolve.api import CodeEvolve
    from codeevolve.eval.scorecard import _analyze_at
    from codeevolve.ingest.github import clone_or_update, github_owner_repo
    from codeevolve.provenance.ledger import build_provenance_ledger
    from codeevolve.provenance.schema import validate_deliberation_pack

    gh = github_owner_repo(args.repo)
    if not gh:
        print(f"Invalid repo: {args.repo}", file=sys.stderr)
        return 2
    owner, name = gh
    print(f"Cloning/updating {owner}/{name} …")
    repo = clone_or_update(owner, name, depth=800, full=False)

    print(f"Analyzing at {args.ref} (max_commits={args.max_commits}) …")
    # Detached checkout at the tag — same path as evaluate --suite dynamics
    data = _analyze_at(repo, rev=args.ref, max_commits=args.max_commits)
    # Rebuild rich objects for pretty demo (analyze_at returns dict)
    report_ns = type("R", (), {})()
    report_ns.dynamics = data.get("dynamics") or {}
    report_ns.blast_radius = data.get("blast_radius") or []
    tax = data.get("taxonomy") or {}
    clades = tax.get("clades") or []

    class _C:
        def __init__(self, d):
            self.files = d.get("files") or []

    report_ns.taxonomy = type("T", (), {"clades": [_C(c) for c in clades if isinstance(c, dict)]})()
    ledger = build_provenance_ledger(data)
    report_ns.provenance = ledger

    dyn = report_ns.dynamics or {}
    print("\n=== Dynamics (real history) ===")
    print(dyn.get("summary") or "(no dynamics)")
    print(
        f"samples={dyn.get('sample_count')} impulses={dyn.get('impulse_count')} "
        f"basins={dyn.get('basin_count')} episodes={dyn.get('episode_count')} "
        f"insufficient={dyn.get('insufficient')}"
    )

    print("\n=== Deliberation frames (top) ===")
    for f in ledger.frames[:8]:
        print(f"- {f.id} [{f.stance}@{f.confidence:.2f}] {f.claim[:100]}")
        if f.falsifier:
            print(f"    falsifier: {f.falsifier[:90]}")

    impulses = [r for r in ledger.records if r.kind == "impulse_response"][:3]
    if impulses:
        print("\n=== Impulse responses (sample) ===")
        for r in impulses:
            print(f"- {r.label}: {r.summary}")

    basins = [r for r in ledger.records if r.kind == "regime_basin"][:3]
    if basins:
        print("\n=== Regime basins ===")
        for r in basins:
            print(f"- {r.label}: {r.summary}")

    focus = args.path
    if not focus:
        br = report_ns.blast_radius[0]["path"] if report_ns.blast_radius else None
        focus = br or (
            report_ns.taxonomy.clades[0].files[0]
            if report_ns.taxonomy.clades and report_ns.taxonomy.clades[0].files
            else None
        )
    if focus:
        print(f"\n=== Path pack: {focus} ===")
        pp = ledger.path_pack(focus)
        print(f"clade={pp.get('clade_id')} episodes={len(pp.get('episodes') or [])}")
        if pp.get("blast_radius"):
            print(f"blast={pp['blast_radius'].get('summary')}")
        for q in (pp.get("suggested_questions") or [])[:3]:
            print(f"? {q}")

    pack = ledger.deliberation_pack(path=focus)
    errs = validate_deliberation_pack(pack)
    print(f"\n=== Pack schema: {'OK' if not errs else errs} ===")
    print("howto:", pack.get("howto"))

    if args.out:
        Path(args.out).write_text(json.dumps(pack, indent=2, default=str), encoding="utf-8")
        print(f"Wrote {args.out}")

    print("\nNext:")
    print(f"  python -m codeevolve --repo {args.repo} provenance --pack --frame frame:basin")
    print("  python -m codeevolve evaluate --suite dynamics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
