"""Propose bounded code improvements from provenance + refactor steps."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.agent.patch import parse_unified_patches, patches_to_file_edits
from codeevolve.agent.toolcall import llm_tool_loop
from codeevolve.agent.tools.registry import ToolRegistry, build_default_registry
from codeevolve.agent.workspace import FileEdit, Workspace, edits_from_proposals, parse_unified_diff
from codeevolve.models.backends import get_chat_backend
from codeevolve.models.endpoints import EndpointConfig


@dataclass
class ActionProposal:
    step_id: str
    title: str
    paths: list[str]
    frame_ids: list[str]
    evidence_refs: list[str]
    rationale: str
    falsifier: str
    measure: str
    edits: list[FileEdit] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    backend: str = "heuristic"
    stance: str = "proceed"  # proceed | insufficient | defer
    endpoint: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "title": self.title,
            "paths": list(self.paths),
            "frame_ids": list(self.frame_ids),
            "evidence_refs": list(self.evidence_refs),
            "rationale": self.rationale,
            "falsifier": self.falsifier,
            "measure": self.measure,
            "edits": [e.to_dict() for e in self.edits],
            "edit_previews": [
                {"path": e.path, "mode": e.mode, "content": e.content[:4000]} for e in self.edits
            ],
            "instructions": list(self.instructions),
            "backend": self.backend,
            "stance": self.stance,
            "endpoint": dict(self.endpoint),
        }


def _frame_bits(path_pack: dict[str, Any] | None, pack: dict[str, Any] | None) -> tuple[list[str], str, str]:
    frames = []
    falsifier = "If next CodeEvolve run does not improve the targeted signal, reject this change."
    measure = "Re-analyze with --previous and score the objective."
    source = path_pack or pack or {}
    for fr in (source.get("frames") or [])[:8]:
        if isinstance(fr, dict) and fr.get("id"):
            frames.append(str(fr["id"]))
            if fr.get("falsifier"):
                falsifier = str(fr["falsifier"])
            if fr.get("measure"):
                measure = str(fr["measure"])
    howto = source.get("howto")
    if isinstance(howto, dict) and howto.get("falsifier"):
        falsifier = str(howto["falsifier"])
    return frames, falsifier, measure


def _py_module_import_path(rel: str) -> str:
    p = rel.replace("\\", "/")
    if p.endswith(".py"):
        p = p[:-3]
    return p.replace("/", ".")


def heuristic_propose(
    workspace: Workspace,
    step: dict[str, Any],
    *,
    path_pack: dict[str, Any] | None = None,
    pack: dict[str, Any] | None = None,
) -> ActionProposal:
    paths = [str(p) for p in (step.get("paths") or []) if p]
    if not paths:
        # fall back to hot files mentioned in actions
        for a in step.get("actions") or []:
            m = re.search(r"([\w./\\-]+\.py)", str(a))
            if m:
                paths.append(m.group(1).replace("\\", "/"))
    kind = str(step.get("problem_kind") or "")
    frames, falsifier, measure = _frame_bits(path_pack, pack)
    edits: list[FileEdit] = []
    instructions = list(step.get("actions") or [])
    stance = "proceed"

    # Prefer first existing path under fence
    target = None
    for p in paths:
        try:
            if workspace.resolve(p).is_file() and workspace.allowed(p):
                target = p
                break
        except ValueError:
            continue

    if kind == "test_gap" or "test" in kind:
        src = target
        if src and src.endswith(".py") and "/test" not in src.replace("\\", "/"):
            name = Path(src).stem
            test_rel = f"tests/test_{name}_codeevolve.py"
            if not (workspace.root / test_rel).exists():
                mod = _py_module_import_path(src)
                content = (
                    f'"""Regression smoke tests seeded by CodeEvolve agent for `{src}`."""\n\n'
                    f"def test_import_{name}():\n"
                    f"    __import__(\"{mod}\")\n"
                )
                # Prefer package-relative import when under src/
                if src.replace("\\", "/").startswith("src/"):
                    content = (
                        f'"""Regression smoke tests seeded by CodeEvolve agent for `{src}`."""\n'
                        f"import sys\n"
                        f"from pathlib import Path\n\n"
                        f"ROOT = Path(__file__).resolve().parents[1]\n"
                        f"sys.path.insert(0, str(ROOT / \"src\"))\n\n"
                        f"def test_import_{name}():\n"
                        f"    __import__(\"{Path(src).stem}\")\n"
                    )
                edits.append(FileEdit(path=test_rel, content=content, mode="create"))
                instructions.append(f"Add smoke test covering import of {src}")
            else:
                stance = "defer"
                instructions.append(f"Test file already exists: {test_rel}")
        else:
            stance = "insufficient"
            instructions.append("No clear source path for test scaffolding")

    elif "debt" in kind or kind.startswith("deprec") or step.get("wave") == "pay_down":
        if target:
            text = workspace.read_text(target)
            if "FIXME" in text or "TODO" in text or "deprecated" in text.lower():
                # Quarantine marker + extract comment into CODEEVOLVE_DEBT.md note section via sidecar
                note_path = ".codeevolve/agent/DEBT_NOTES.md"
                existing = workspace.read_text(note_path) if (workspace.root / note_path).exists() else "# CodeEvolve debt notes\n"
                snippet_lines = [
                    ln for ln in text.splitlines() if re.search(r"FIXME|TODO|deprecated", ln, re.I)
                ][:12]
                block = (
                    f"\n## {target}\n\n"
                    f"- step: {step.get('id')}\n"
                    f"- evidence: {', '.join(str(x) for x in (step.get('evidence_refs') or [])[:6])}\n"
                    + "\n".join(f"  - `{ln.strip()}`" for ln in snippet_lines)
                    + "\n"
                )
                if f"## {target}" not in existing:
                    edits.append(FileEdit(path=note_path, content=existing + block, mode="write"))
                    instructions.append(f"Catalog debt markers from {target} into {note_path}")
                else:
                    stance = "defer"
                    instructions.append("Debt notes already captured for path")
            else:
                stance = "insufficient"
                instructions.append("No debt markers found in target file; record insufficient")
        else:
            stance = "insufficient"

    elif kind in {"hotspot_blast", "change_coupling", "hotspot_gravity", "utility_sink"} or step.get("wave") == "contain":
        if target:
            text = workspace.read_text(target)
            fence_doc = ".codeevolve/agent/PATH_FENCE.md"
            existing = workspace.read_text(fence_doc) if (workspace.root / fence_doc).exists() else "# Path fence\n"
            section = (
                f"\n## Fence: {target}\n\n"
                f"- step: `{step.get('id')}` — {step.get('title')}\n"
                f"- frames: {', '.join(frames) or 'n/a'}\n"
                f"- rule: prefer small changes; no new cross-module imports without tests\n"
                f"- size: {len(text.splitlines())} lines\n"
            )
            if f"## Fence: {target}" not in existing:
                edits.append(FileEdit(path=fence_doc, content=existing + section, mode="write"))
                instructions.append(
                    f"Contain change surface on {target}; expand only with path-pack evidence"
                )
            else:
                stance = "defer"
        else:
            stance = "insufficient"

    else:
        # Generic: write a bounded improvement brief the LLM/human can execute
        brief = ".codeevolve/agent/NEXT_ACTION.md"
        body = (
            f"# Next action\n\n"
            f"- id: `{step.get('id')}`\n"
            f"- title: {step.get('title')}\n"
            f"- wave: {step.get('wave')}\n"
            f"- kind: {kind}\n"
            f"- paths: {', '.join(paths) or '(none)'}\n"
            f"- frames: {', '.join(frames) or '(none)'}\n\n"
            f"## Actions\n"
            + "\n".join(f"- {a}" for a in (step.get("actions") or [])[:8])
            + "\n\n## Acceptance\n"
            + "\n".join(f"- {c}" for c in (step.get("acceptance_criteria") or [])[:6])
            + f"\n\n## Falsifier\n\n{falsifier}\n\n## Measure\n\n{measure}\n"
        )
        edits.append(FileEdit(path=brief, content=body, mode="write"))
        if not paths:
            stance = "insufficient"

    rationale = (
        f"Heuristic actor selected step {step.get('id')} ({kind or step.get('wave')}) "
        f"using frames {', '.join(frames) or 'none'}; stance={stance}."
    )
    return ActionProposal(
        step_id=str(step.get("id") or "step"),
        title=str(step.get("title") or "improve"),
        paths=paths or [e.path for e in edits],
        frame_ids=frames,
        evidence_refs=[str(x) for x in (step.get("evidence_refs") or [])],
        rationale=rationale,
        falsifier=falsifier,
        measure=measure,
        edits=edits,
        instructions=instructions,
        backend="heuristic",
        stance=stance,
    )


def llm_propose(
    workspace: Workspace,
    step: dict[str, Any],
    *,
    objective: dict[str, Any],
    path_pack: dict[str, Any] | None = None,
    pack: dict[str, Any] | None = None,
    llm: str | bool | None = "auto",
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    repo: Path | str | None = None,
    tools: ToolRegistry | None = None,
    budget: Any = None,
    structured_tools: bool = True,
) -> ActionProposal:
    """LLM proposal via structured tool calls (preferred) or FILE:/END FILE fallback."""
    base = heuristic_propose(workspace, step, path_pack=path_pack, pack=pack)
    backend = get_chat_backend(
        llm if llm is not None else "auto",
        model=model,
        base_url=base_url,
        api_key=api_key,
        repo=repo or workspace.root,
    )
    endpoint: EndpointConfig = getattr(backend, "endpoint", None) or EndpointConfig(
        provider=backend.name, kind="heuristic", model="heuristic"
    )
    ep_dict = endpoint.to_dict()
    if backend.name == "heuristic" or endpoint.kind == "heuristic":
        base.endpoint = ep_dict
        base.instructions.append(
            f"No LLM endpoint configured (resolved={endpoint.provider}); heuristic proposal only. "
            "Set --provider/--llm or API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, XAI_API_KEY, MOONSHOT_API_KEY)."
        )
        return base

    paths = base.paths[:4] or list(workspace.fence_paths)[:4]
    files = {p: workspace.read_text(p, max_chars=8000) for p in paths if p}
    frames, falsifier, measure = _frame_bits(path_pack, pack)
    label = f"{endpoint.provider}:{endpoint.model}"
    reg = tools or build_default_registry(workspace.root, allow_web=False, allow_shell=False)

    if structured_tools:
        out = llm_tool_loop(
            system_extra=(
                f"Respect falsifier: {falsifier}. Path fence: {workspace.fence_paths}. "
                "Use apply_patch with unified diff hunks when possible."
            ),
            user_payload={
                "objective": objective,
                "step": {
                    k: step.get(k)
                    for k in ("id", "title", "wave", "problem_kind", "actions", "acceptance_criteria", "paths")
                },
                "frame_ids": frames,
                "falsifier": falsifier,
                "measure": measure,
                "path_fence": workspace.fence_paths,
                "files": files,
            },
            tools=reg,
            workspace=workspace,
            provider=llm,
            model=model,
            base_url=base_url,
            api_key=api_key,
            repo=repo or workspace.root,
            max_turns=3,
            budget=budget,
        )
        edits = [e for e in (out.get("edit_objects") or []) if workspace.allowed(e.path)]
        if not edits and out.get("patch_objects"):
            edits = [
                e
                for e in patches_to_file_edits(workspace, out["patch_objects"])
                if workspace.allowed(e.path)
            ]
        if edits:
            return ActionProposal(
                step_id=base.step_id,
                title=base.title,
                paths=[e.path for e in edits],
                frame_ids=frames or base.frame_ids,
                evidence_refs=base.evidence_refs,
                rationale=f"Structured tool-loop ({label}): {out.get('summary') or 'apply_patch'}",
                falsifier=falsifier,
                measure=measure,
                edits=edits,
                instructions=base.instructions
                + [f"tool_calls={len(out.get('results') or [])}", f"summary={out.get('summary')}"],
                backend=f"{backend.name}+tools",
                stance="proceed",
                endpoint=ep_dict,
            )

    # Fallback: free-form FILE/END FILE or unified diff text
    system = (
        "You are a coding agent guided by CodeEvolve evolutionary provenance. "
        "Propose minimal safe edits. Prefer unified diff hunks or FILE:/END FILE. "
        "Respect the falsifier. Stay inside the path fence."
    )
    payload = {
        "objective": objective,
        "step": {
            k: step.get(k)
            for k in ("id", "title", "wave", "problem_kind", "actions", "acceptance_criteria", "paths")
        },
        "frame_ids": frames,
        "falsifier": falsifier,
        "path_fence": workspace.fence_paths,
        "files": files,
    }
    text = backend.complete(system, json.dumps(payload, default=str), max_tokens=4096)
    if budget is not None:
        budget.record_llm(
            provider=endpoint.provider,
            model=endpoint.model,
            tokens_in=max(1, len(system + str(payload)) // 4),
            tokens_out=max(1, len(text) // 4),
            label="llm_propose_fallback",
        )
    edits = []
    for patch in parse_unified_patches(text):
        edits.extend(patches_to_file_edits(workspace, [patch]))
    if not edits:
        for path, content in parse_unified_diff(text):
            if workspace.allowed(path):
                edits.append(FileEdit(path=path, content=content, mode="write"))
    edits = [e for e in edits if workspace.allowed(e.path)]
    if not edits:
        base.instructions.append(f"LLM ({label}) produced no patches; kept heuristic proposal")
        base.backend = f"{backend.name}+heuristic"
        base.endpoint = ep_dict
        return base

    return ActionProposal(
        step_id=base.step_id,
        title=base.title,
        paths=[e.path for e in edits],
        frame_ids=frames or base.frame_ids,
        evidence_refs=base.evidence_refs,
        rationale=f"LLM ({label}) patch proposal constrained by path fence and frames.",
        falsifier=falsifier,
        measure=measure,
        edits=edits,
        instructions=base.instructions + [f"Parsed patches via {label}"],
        backend=backend.name,
        stance="proceed",
        endpoint=ep_dict,
    )


def propose_action(
    workspace: Workspace,
    step: dict[str, Any],
    *,
    objective: dict[str, Any],
    path_pack: dict[str, Any] | None = None,
    pack: dict[str, Any] | None = None,
    llm: str | bool | None = "auto",
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    repo: Path | str | None = None,
    tools: ToolRegistry | None = None,
    budget: Any = None,
    structured_tools: bool = True,
) -> ActionProposal:
    """Propose an action. Default ``llm='auto'`` selects SLM/GPU/cloud from config."""
    if llm is False or llm == "heuristic" or llm == "off":
        prop = heuristic_propose(workspace, step, path_pack=path_pack, pack=pack)
        prop.endpoint = {"provider": "heuristic", "kind": "heuristic", "model": "heuristic"}
        return prop
    return llm_propose(
        workspace,
        step,
        objective=objective,
        path_pack=path_pack,
        pack=pack,
        llm="auto" if llm is None or llm is True else llm,
        model=model,
        base_url=base_url,
        api_key=api_key,
        repo=repo,
        tools=tools,
        budget=budget,
        structured_tools=structured_tools,
    )
