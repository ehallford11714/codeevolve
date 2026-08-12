"""Structured JSON tool-calling protocol for the coding LLM."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from codeevolve.agent.patch import FilePatch, parse_unified_patches
from codeevolve.agent.tools.registry import ToolRegistry, ToolResult
from codeevolve.agent.workspace import FileEdit, Workspace, edits_from_proposals
from codeevolve.models.backends import get_chat_backend


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "grep",
        "description": "Search repo content by regex",
        "parameters": {"pattern": "string", "path": "string?", "max_hits": "integer?"},
    },
    {
        "name": "file_read",
        "description": "Read a file",
        "parameters": {"path": "string", "max_chars": "integer?"},
    },
    {
        "name": "file_list",
        "description": "List files",
        "parameters": {"path": "string?", "glob": "string?"},
    },
    {
        "name": "rag_query",
        "description": "Semantic chunk retrieval",
        "parameters": {"query": "string", "top_k": "integer?"},
    },
    {
        "name": "morpheme_scan",
        "description": "Ontology/morpheme scan",
        "parameters": {"paths": "array?"},
    },
    {
        "name": "provenance_hint",
        "description": "Deliberation / path pack frames",
        "parameters": {"path": "string?"},
    },
    {
        "name": "web_search",
        "description": "Web search",
        "parameters": {"query": "string", "max_results": "integer?"},
    },
    {
        "name": "memory_search",
        "description": "Search agent memory",
        "parameters": {"query": "string"},
    },
    {
        "name": "memory_add",
        "description": "Add memory note",
        "parameters": {"content": "string", "kind": "string?"},
    },
    {
        "name": "apply_patch",
        "description": "Propose a unified diff or FILE/END FILE edits (does not write until approved)",
        "parameters": {
            "diff": "string?",
            "edits": "array?",  # [{path, content, mode?}]
            "symbol": "string?",  # optional symbol fence qualname
        },
    },
    {
        "name": "done",
        "description": "Finish with rationale",
        "parameters": {"summary": "string", "stance": "string?"},
    },
]


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "arguments": dict(self.arguments)}


@dataclass
class ToolCallTurn:
    calls: list[ToolCall] = field(default_factory=list)
    raw: str = ""
    parse_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "calls": [c.to_dict() for c in self.calls],
            "parse_error": self.parse_error,
            "raw_excerpt": self.raw[:1500],
        }


def parse_tool_calls(text: str) -> ToolCallTurn:
    """Parse model output into tool calls. Accepts JSON object/array or TOOL_CALL blocks."""
    turn = ToolCallTurn(raw=text or "")
    if not text:
        turn.parse_error = "empty"
        return turn

    # fenced json
    candidates = []
    for m in re.finditer(r"```(?:json)?\n([\s\S]*?)```", text):
        candidates.append(m.group(1).strip())
    candidates.append(text.strip())

    for cand in candidates:
        # array of calls
        try:
            start = cand.find("[")
            end = cand.rfind("]")
            if start >= 0 and end > start:
                data = json.loads(cand[start : end + 1])
                if isinstance(data, list):
                    for row in data:
                        if isinstance(row, dict) and row.get("name"):
                            turn.calls.append(
                                ToolCall(
                                    name=str(row["name"]),
                                    arguments=dict(row.get("arguments") or row.get("args") or {}),
                                )
                            )
                    if turn.calls:
                        return turn
        except json.JSONDecodeError:
            pass
        # {"tool_calls":[...]} or single {"name":...}
        try:
            start = cand.find("{")
            end = cand.rfind("}")
            if start >= 0 and end > start:
                data = json.loads(cand[start : end + 1])
                if isinstance(data, dict):
                    if "tool_calls" in data and isinstance(data["tool_calls"], list):
                        for row in data["tool_calls"]:
                            if isinstance(row, dict) and row.get("name"):
                                turn.calls.append(
                                    ToolCall(
                                        name=str(row["name"]),
                                        arguments=dict(row.get("arguments") or row.get("args") or {}),
                                    )
                                )
                        if turn.calls:
                            return turn
                    if data.get("name"):
                        turn.calls.append(
                            ToolCall(
                                name=str(data["name"]),
                                arguments=dict(data.get("arguments") or data.get("args") or {}),
                            )
                        )
                        return turn
        except json.JSONDecodeError:
            pass

    # TOOL_CALL name {...}
    for m in re.finditer(
        r"TOOL_CALL\s+(?P<name>[A-Za-z_][\w]*)\s+(?P<body>\{[\s\S]*?\})(?=\s*TOOL_CALL|\s*$)",
        text,
    ):
        try:
            args = json.loads(m.group("body"))
            turn.calls.append(ToolCall(name=m.group("name"), arguments=args if isinstance(args, dict) else {}))
        except json.JSONDecodeError:
            continue
    if turn.calls:
        return turn
    turn.parse_error = "no structured tool calls found"
    return turn


def run_tool_calls(
    turn: ToolCallTurn,
    tools: ToolRegistry,
    *,
    workspace: Workspace | None = None,
) -> tuple[list[dict[str, Any]], list[FileEdit], list[FilePatch], str | None]:
    """Execute calls; collect edits/patches from apply_patch; return done summary."""
    results: list[dict[str, Any]] = []
    edits: list[FileEdit] = []
    patches: list[FilePatch] = []
    done_summary = None
    for call in turn.calls:
        if call.name == "done":
            done_summary = str(call.arguments.get("summary") or "done")
            results.append({"call": call.to_dict(), "result": {"ok": True, "output": done_summary}})
            continue
        if call.name == "apply_patch":
            diff = call.arguments.get("diff")
            raw_edits = call.arguments.get("edits")
            if diff:
                parsed = parse_unified_patches(str(diff))
                patches.extend(parsed)
                if workspace is not None:
                    from codeevolve.agent.patch import patches_to_file_edits

                    edits.extend(patches_to_file_edits(workspace, parsed))
            if isinstance(raw_edits, list):
                edits.extend(edits_from_proposals(raw_edits))
            results.append(
                {
                    "call": call.to_dict(),
                    "result": {
                        "ok": True,
                        "output": {"patches": len(patches), "edits": len(edits)},
                    },
                }
            )
            continue
        # strip unknown keys
        res: ToolResult = tools.call(call.name, **call.arguments)
        results.append({"call": call.to_dict(), "result": res.to_dict()})
    return results, edits, patches, done_summary


def llm_tool_loop(
    *,
    system_extra: str,
    user_payload: dict[str, Any],
    tools: ToolRegistry,
    workspace: Workspace,
    provider: str | bool | None = "auto",
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    repo: Any = None,
    max_turns: int = 3,
    budget: Any = None,
) -> dict[str, Any]:
    """Multi-turn structured tool loop until done or max_turns."""
    backend = get_chat_backend(provider, model=model, base_url=base_url, api_key=api_key, repo=repo)
    system = (
        "You are a CodeEvolve coding agent. Use ONLY structured tool calls. "
        "Respond with a JSON array of {\"name\", \"arguments\"} objects. "
        "Available tools:\n"
        + json.dumps(TOOL_SCHEMAS, indent=2)
        + "\nPrefer grep/rag/file_read before apply_patch. "
        "apply_patch should use unified diff hunks when possible. "
        "Finish with {\"name\":\"done\",\"arguments\":{\"summary\":\"...\"}}.\n"
        + system_extra
    )
    messages_user = json.dumps(user_payload, default=str)
    all_results: list[dict[str, Any]] = []
    edits: list[FileEdit] = []
    patches: list[FilePatch] = []
    summary = None
    endpoint = getattr(backend, "endpoint", None)

    for turn_i in range(max_turns):
        text = backend.complete(system, messages_user, max_tokens=4096)
        if budget is not None and endpoint is not None:
            # rough token estimate
            tin = max(1, len(messages_user) // 4)
            tout = max(1, len(text) // 4)
            budget.record_llm(
                provider=getattr(endpoint, "provider", backend.name),
                model=getattr(endpoint, "model", ""),
                tokens_in=tin,
                tokens_out=tout,
                label=f"tool_turn_{turn_i}",
            )
        turn = parse_tool_calls(text)
        if turn.parse_error and not turn.calls:
            all_results.append({"turn": turn_i, "error": turn.parse_error, "raw": text[:800]})
            break
        res, e, p, done = run_tool_calls(turn, tools, workspace=workspace)
        all_results.extend(res)
        edits.extend(e)
        patches.extend(p)
        if done:
            summary = done
            break
        # feed observations back
        messages_user = json.dumps(
            {"prior": user_payload, "observations": res, "note": "Continue or call done"},
            default=str,
        )[:14000]

    return {
        "backend": backend.name,
        "endpoint": endpoint.to_dict() if endpoint and hasattr(endpoint, "to_dict") else {},
        "results": all_results,
        "edits": [e.to_dict() for e in edits],
        "edit_objects": edits,
        "patches": [p.to_dict() for p in patches],
        "patch_objects": patches,
        "summary": summary,
        "schemas": TOOL_SCHEMAS,
    }
