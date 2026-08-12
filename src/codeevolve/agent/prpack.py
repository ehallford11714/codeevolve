"""Deliberation-backed PR / review pack from an AgentRun."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def build_pr_pack(
    run: dict[str, Any],
    *,
    report: dict[str, Any] | None = None,
    diff: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured review pack: frames, falsifiers, scores, CI, paths."""
    rounds = run.get("rounds") or []
    accepted = [r for r in rounds if r.get("accepted")]
    proposals = []
    frame_ids: list[str] = []
    falsifiers: list[str] = []
    paths: list[str] = []
    for r in rounds:
        prop = r.get("proposal") or {}
        if not prop:
            continue
        fids = list(prop.get("frame_ids") or [])
        frame_ids.extend(fids)
        if prop.get("falsifier"):
            falsifiers.append(str(prop["falsifier"]))
        for p in prop.get("paths") or []:
            if p and p not in paths:
                paths.append(str(p))
        proposals.append(
            {
                "round": r.get("index"),
                "step_id": r.get("step_id"),
                "accepted": r.get("accepted"),
                "stance": prop.get("stance"),
                "frame_ids": fids,
                "falsifier": prop.get("falsifier"),
                "measure": prop.get("measure"),
                "rationale": (prop.get("rationale") or "")[:400],
                "paths": prop.get("paths") or [],
                "score_before": r.get("score_before"),
                "score_after": r.get("score_after"),
                "verify_ok": r.get("verify_ok"),
                "notes": r.get("notes") or [],
            }
        )

    # Dedup frame ids preserving order
    seen: set[str] = set()
    uniq_frames: list[str] = []
    for fid in frame_ids:
        if fid not in seen:
            seen.add(fid)
            uniq_frames.append(fid)

    pack = {
        "kind": "codeevolve_pr_pack",
        "objective": run.get("objective"),
        "status": run.get("status"),
        "summary": run.get("summary"),
        "endpoint": run.get("endpoint"),
        "git": run.get("git"),
        "budget": run.get("budget"),
        "tests": run.get("tests"),
        "final_score": run.get("final_score"),
        "accepted_rounds": len(accepted),
        "total_rounds": len(rounds),
        "frame_ids": uniq_frames,
        "falsifiers": list(dict.fromkeys(falsifiers))[:12],
        "paths": paths[:40],
        "proposals": proposals,
        "diff": diff,
        "report_signals": _report_signals(report) if report else None,
    }
    return pack


def render_pr_pack_markdown(pack: dict[str, Any]) -> str:
    """Markdown body suitable for gh pr create/comment."""
    obj = pack.get("objective") or {}
    lines = [
        "## CodeEvolve agent review pack",
        "",
        f"- **Objective:** `{obj.get('kind')}` — {(obj.get('description') or '')[:160]}",
        f"- **Status:** `{pack.get('status')}` · accepted={pack.get('accepted_rounds')}/{pack.get('total_rounds')}",
        f"- **Final score:** `{((pack.get('final_score') or {}).get('value'))}`",
    ]
    git = pack.get("git") or {}
    if git.get("work_branch"):
        lines.append(f"- **Work branch:** `{git.get('work_branch')}` (base `{git.get('base_branch')}`)")
    tests = pack.get("tests") or {}
    if tests:
        score = tests.get("score") or {}
        lines.append(
            f"- **Tests:** ok={score.get('ok')} value={score.get('value')} "
            f"coverage={score.get('coverage')}"
        )
    budget = pack.get("budget") or {}
    if budget:
        lines.append(f"- **Cost:** ${budget.get('cost_usd')} · rounds={budget.get('rounds_used')}")

    frames = pack.get("frame_ids") or []
    if frames:
        lines += ["", "### Frames"]
        for fid in frames[:12]:
            lines.append(f"- `{fid}`")
    fals = pack.get("falsifiers") or []
    if fals:
        lines += ["", "### Falsifiers"]
        for f in fals[:8]:
            lines.append(f"- {f}")

    if pack.get("paths"):
        lines += ["", "### Paths touched"]
        for p in pack["paths"][:20]:
            lines.append(f"- `{p}`")

    sig = pack.get("report_signals") or {}
    if sig:
        lines += [
            "",
            "### Report signals",
            f"- stage=`{sig.get('stage')}` stability=`{sig.get('stability')}` "
            f"debt=`{sig.get('debt')}` risk_count=`{sig.get('risk_count')}`",
        ]

    diff = pack.get("diff") or {}
    if diff:
        lines += ["", "### Since previous report"]
        for x in (diff.get("improved") or [])[:6]:
            lines.append(f"- Improved: {x}")
        for x in (diff.get("worsened") or [])[:6]:
            lines.append(f"- Worsened: {x}")

    props = pack.get("proposals") or []
    if props:
        lines += ["", "### Rounds"]
        for p in props:
            mark = "✓" if p.get("accepted") else "·"
            lines.append(
                f"- {mark} round {p.get('round')} `{p.get('step_id')}` "
                f"stance={p.get('stance')} frames={','.join(p.get('frame_ids') or []) or '—'}"
            )
            if p.get("falsifier"):
                lines.append(f"  - falsifier: {p['falsifier']}")
            if p.get("score_after"):
                lines.append(
                    f"  - score: {(p.get('score_before') or {}).get('value')} → "
                    f"{(p.get('score_after') or {}).get('value')}"
                )

    lines += [
        "",
        "_Inspect with `codeevolve provenance --frame <id>` / `--path-pack`. "
        "Do not invent history beyond cited frames._",
        "",
        "_Generated by [CodeEvolve](https://github.com/ehallford11714/codeevolve)_",
        "",
    ]
    return "\n".join(lines)


def write_pr_pack(
    run: dict[str, Any],
    dest_dir: Path | str,
    *,
    report: dict[str, Any] | None = None,
    diff: dict[str, Any] | None = None,
) -> dict[str, str]:
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    pack = build_pr_pack(run, report=report, diff=diff)
    md = render_pr_pack_markdown(pack)
    json_path = dest / "pr_pack.json"
    md_path = dest / "pr_pack.md"
    json_path.write_text(json.dumps(pack, indent=2, default=str), encoding="utf-8")
    md_path.write_text(md, encoding="utf-8")
    return {"json": str(json_path), "md": str(md_path)}


def post_pr_comment(
    body_md: str | Path,
    *,
    pr: int | str | None = None,
    repo: Path | str | None = None,
) -> dict[str, Any]:
    """Post via `gh pr comment` when available. Never invents content."""
    body_path: Path
    if isinstance(body_md, Path) or (isinstance(body_md, str) and Path(body_md).is_file()):
        body_path = Path(body_md)
        body = body_path.read_text(encoding="utf-8")
    else:
        body = str(body_md)
        body_path = Path(repo or ".") / ".codeevolve" / "agent" / "pr_pack.md"
        body_path.parent.mkdir(parents=True, exist_ok=True)
        body_path.write_text(body, encoding="utf-8")

    cmd = ["gh", "pr", "comment"]
    if pr is not None:
        cmd.append(str(pr))
    cmd += ["--body-file", str(body_path)]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo) if repo else None,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": str(exc), "body_file": str(body_path)}
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[:500],
        "stderr": (proc.stderr or "")[:500],
        "body_file": str(body_path),
    }


def _report_signals(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "stage": (report.get("ecology") or {}).get("global_stage")
        or (report.get("phylogeny") or {}).get("current_stage"),
        "stability": (report.get("stability") or {}).get("composite"),
        "debt": (report.get("debt") or {}).get("score"),
        "risk_count": len((report.get("risk") or {}).get("failure_points") or []),
    }
