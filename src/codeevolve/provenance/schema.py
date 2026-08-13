"""JSON Schema + MCP tool descriptors for provenance deliberation packs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schemas"

DELIBERATION_PACK_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://codeevolve.dev/schemas/deliberation_pack.schema.json",
    "title": "CodeEvolveDeliberationPack",
    "type": "object",
    "required": ["repo", "frames", "howto"],
    "properties": {
        "repo": {"type": "string"},
        "summary": {"type": "string"},
        "focus": {
            "type": "object",
            "properties": {
                "path": {"type": ["string", "null"]},
                "clade": {"type": ["string", "null"]},
            },
        },
        "frames": {
            "type": "array",
            "items": {"$ref": "#/$defs/frame"},
        },
        "records": {
            "type": "array",
            "items": {"$ref": "#/$defs/record"},
        },
        "timeline": {"type": "array"},
        "path_focus": {"type": ["object", "null"]},
        "howto": {"type": "string"},
    },
    "$defs": {
        "evidence": {
            "type": "object",
            "required": ["record_id", "kind", "role"],
            "properties": {
                "record_id": {"type": "string"},
                "kind": {"type": "string"},
                "role": {"type": "string"},
                "note": {"type": "string"},
            },
        },
        "frame": {
            "type": "object",
            "required": ["id", "claim", "stance", "confidence", "evidence"],
            "properties": {
                "id": {"type": "string"},
                "claim": {"type": "string"},
                "stance": {"type": "string"},
                "confidence": {"type": "number"},
                "evidence": {"type": "array", "items": {"$ref": "#/$defs/evidence"}},
                "falsifier": {"type": "string"},
                "measure": {"type": "string"},
                "suggested_questions": {"type": "array", "items": {"type": "string"}},
                "context_paths": {"type": "array", "items": {"type": "string"}},
                "context_clades": {"type": "array", "items": {"type": "string"}},
            },
        },
        "record": {
            "type": "object",
            "required": ["id", "kind"],
            "properties": {
                "id": {"type": "string"},
                "kind": {"type": "string"},
                "when": {"type": ["string", "null"]},
                "path": {"type": ["string", "null"]},
                "clade_id": {"type": ["string", "null"]},
                "sha": {"type": ["string", "null"]},
                "label": {"type": "string"},
                "summary": {"type": "string"},
                "confidence": {"type": ["number", "null"]},
                "tags": {"type": "array", "items": {"type": "string"}},
                "payload": {"type": "object"},
                "links": {"type": "array", "items": {"$ref": "#/$defs/evidence"}},
            },
        },
    },
}

MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "analyze_repo",
        "description": (
            "Analyze a local path or GitHub repo/url with CodeEvolve. Writes report.json "
            "(and optional deliberation pack). Use this first before provenance_* tools "
            "when parsing an unfamiliar codebase."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["repo"],
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Local path, owner/name, or https://github.com/… URL",
                },
                "max_commits": {"type": "integer", "default": 200},
                "out": {
                    "type": "string",
                    "description": "Where to write report.json (default: .codeevolve/report.json under cwd or repo)",
                },
                "pack_out": {
                    "type": "string",
                    "description": "Optional path to write deliberation pack JSON",
                },
                "path": {
                    "type": "string",
                    "description": "Optional path focus included in returned pack",
                },
            },
        },
    },
    {
        "name": "provenance_pack",
        "description": (
            "Build a deliberation pack from a CodeEvolve report.json. "
            "Returns frames with claim→evidence→falsifier for agent deliberation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_report": {"type": "string", "description": "Path to report.json"},
                "path": {"type": "string", "description": "Optional path focus"},
                "clade": {"type": "string"},
            },
        },
    },
    {
        "name": "provenance_expand_frame",
        "description": "Expand a deliberation frame id with evidence records, chain, and timeline.",
        "inputSchema": {
            "type": "object",
            "required": ["frame"],
            "properties": {
                "from_report": {"type": "string"},
                "frame": {"type": "string", "description": "e.g. frame:basin"},
            },
        },
    },
    {
        "name": "provenance_path_pack",
        "description": (
            "Path-centric provenance for a file/dir: lineage, episodes, blast, symbols, frames. "
            "Use before editing a hotspot."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["path"],
            "properties": {
                "from_report": {"type": "string"},
                "path": {"type": "string"},
                "clade": {"type": "string"},
            },
        },
    },
    {
        "name": "provenance_resolve",
        "description": "Walk evidence links from a record or frame id.",
        "inputSchema": {
            "type": "object",
            "required": ["resolve"],
            "properties": {
                "from_report": {"type": "string"},
                "resolve": {"type": "string"},
                "depth": {"type": "integer", "default": 2},
            },
        },
    },
    {
        "name": "provenance_timeline",
        "description": "Chronological provenance slice (state samples + lifecycle events).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_report": {"type": "string"},
                "path": {"type": "string"},
                "clade": {"type": "string"},
            },
        },
    },
    {
        "name": "viz_phylogeny",
        "description": (
            "Render 3D phylogeny builder (semantic type_path divisions + intent + analysis) or 2D "
            "clade / Fitch / gene-flow SVG+HTML from a report.json. Each tree split is a keyword "
            "type_path taxon (domain/family/kind/specialty) voted from allocated paths; Fitch "
            "reconstructs each ontology depth. Writes a gallery (or SVG/Newick). Use after analyze_repo. "
            "Does not invent history — silent types stay insufficient."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_report": {"type": "string", "description": "Path to report.json"},
                "out": {
                    "type": "string",
                    "description": "HTML/SVG/JSON/Newick file or directory (default .codeevolve/viz.html)",
                },
                "kind": {
                    "type": "string",
                    "default": "all",
                    "description": "all | 3d | phylogeny | clades | parsimony | gene-flow",
                },
                "format": {
                    "type": "string",
                    "default": "html",
                    "description": "html | svg | json | newick",
                },
                "collapse_unary": {
                    "type": "boolean",
                    "default": False,
                    "description": "Hide unary same-type chains on large DAGs",
                },
            },
        },
    },
    {
        "name": "evolve_toward_objective",
        "description": (
            "Run the native CodeEvolve coding agent: analyze → provenance frames → "
            "bounded proposal/edits → re-score against an objective. "
            "Default is dry-run (proposals only); set apply=true to write files."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["repo"],
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Local path, owner/name, or GitHub URL",
                },
                "objective": {
                    "type": "string",
                    "default": "follow_refactor",
                    "description": (
                        "reduce_debt | raise_stability | reduce_risk | stabilize_path | "
                        "follow_refactor | pass_tests | metric:debt.score:min"
                    ),
                },
                "path": {"type": "string", "description": "Optional path fence"},
                "wave": {
                    "type": "string",
                    "description": "Prefer refactor wave: stabilize|contain|pay_down|evolve",
                },
                "max_rounds": {"type": "integer", "default": 1},
                "max_commits": {"type": "integer", "default": 200},
                "apply": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, write edits and keep only improving rounds",
                },
                "llm": {
                    "type": "string",
                    "default": "auto",
                    "description": (
                        "Provider: auto|slm|hf-qwen|openai|anthropic|grok|kimi|kimik3|"
                        "openrouter|custom|heuristic"
                    ),
                },
                "provider": {
                    "type": "string",
                    "description": "Alias for llm; wins when both set",
                },
                "model": {
                    "type": "string",
                    "description": "Model id override (gpt-4o, claude-sonnet-*, grok-3, kimi-k2, Qwen/…)",
                },
                "base_url": {
                    "type": "string",
                    "description": "OpenAI-compatible API base URL for custom/grok/kimi/etc.",
                },
                "api_key": {
                    "type": "string",
                    "description": "API key override (else provider env vars)",
                },
                "model_tier": {
                    "type": "string",
                    "default": "slm",
                    "description": "Local ladder tier: slm|standard|large|frontier",
                },
                "verify_cmd": {
                    "type": "string",
                    "description": "Shell command that must pass after apply",
                },
                "out": {
                    "type": "string",
                    "description": "Optional path to write AgentRun JSON",
                },
                "cognition": {
                    "type": "boolean",
                    "default": True,
                    "description": "Enable memory/RAG/morpheme/reflect/tools/compact stack",
                },
                "spawn_subagents": {
                    "type": "boolean",
                    "default": True,
                    "description": "Spawn kernel-objective subagents when reflection requests it",
                },
                "allow_web": {"type": "boolean", "default": True},
                "allow_shell": {"type": "boolean", "default": False},
                "rag_backend": {
                    "type": "string",
                    "default": "memory",
                    "description": "RAG vector backend: memory|chromadb|pinecone|auto",
                },
                "max_subagents": {"type": "integer", "default": 3},
                "use_worktree": {
                    "type": "boolean",
                    "default": True,
                    "description": "Use git branch/worktree session when applying",
                },
                "approve": {
                    "type": "boolean",
                    "default": False,
                    "description": "HITL approval before apply",
                },
                "auto_approve": {"type": "boolean", "default": False},
                "max_wall_seconds": {"type": "number"},
                "max_cost_usd": {"type": "number"},
                "run_tests_on_apply": {"type": "boolean", "default": True},
                "parallel_subagents": {"type": "boolean", "default": False},
                "resume": {
                    "type": "boolean",
                    "default": True,
                    "description": "Resume delta analyze from last session report",
                },
                "previous_report": {
                    "type": "string",
                    "description": "Explicit previous report.json for frame:delta:report",
                },
                "prefer_frames": {
                    "type": "boolean",
                    "default": True,
                    "description": "Seed steps from frame:basin / frame:delta",
                },
                "auto_widen_blast": {"type": "boolean", "default": True},
                "refuse_huge_blast": {"type": "boolean", "default": True},
                "write_pr_review": {
                    "type": "boolean",
                    "default": True,
                    "description": "Write deliberation-backed pr_pack.md/json",
                },
            },
        },
    },
    {
        "name": "spawn_kernel_subagents",
        "description": (
            "Spawn CodeEvolve kernel subagents (stabilize/contain/pay_down/investigate/search/…) "
            "with shared in-memory RAG + tooling. Returns findings without applying edits."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["repo"],
            "properties": {
                "repo": {"type": "string"},
                "objective": {"type": "string", "default": "follow_refactor"},
                "kernels": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Kernel names; default = decompose objective",
                },
                "path": {"type": "string"},
                "max_agents": {"type": "integer", "default": 3},
                "allow_web": {"type": "boolean", "default": True},
                "parallel": {
                    "type": "boolean",
                    "default": False,
                    "description": "Run kernel subagents in parallel with path locks",
                },
            },
        },
    },
    {
        "name": "agent_cognition_info",
        "description": "Describe the CodeEvolve agent cognitive stack, tools, and kernel catalog.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "context_graph",
        "description": (
            "Parse a context graph from report.json and/or an agent run dir, then search it. "
            "Families: taxon, context, knowledge, decision, pivot, flow. "
            "Use flow=true for sense→deliberate→act→verify walks; traverse=wave (default) expands hits. "
            "Does not invent history; silent records stay insufficient."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_report": {"type": "string", "description": "Path to report.json"},
                "from_agent": {
                    "type": "string",
                    "description": "Agent dir (.codeevolve/agent) or run.json / cognition.json",
                },
                "previous": {"type": "string", "description": "Previous report.json for delta detection"},
                "search": {"type": "string", "description": "Search query over graph nodes"},
                "flow": {
                    "description": "true, or a query string, to return the agentic flow walk",
                    "oneOf": [{"type": "boolean"}, {"type": "string"}],
                },
                "kernel": {"type": "string", "description": "Focus flow on a kernel (investigate, pay_down, …)"},
                "kind": {"type": "string", "description": "Restrict search to a node kind"},
                "family": {
                    "type": "string",
                    "description": "Family slice/filter: taxon|context|knowledge|decision|pivot|flow",
                },
                "pivot": {"type": "string", "description": "Pivot id or type (choose_path, propose, sense, …)"},
                "precedent": {
                    "description": "true, or a query, for similar past decisions/pivots",
                    "oneOf": [{"type": "boolean"}, {"type": "string"}],
                },
                "delta": {"type": "boolean", "description": "Detect threshold crossings vs previous report"},
                "surface": {"type": "boolean", "description": "Rank delta events for proactive surfacing"},
                "traverse": {
                    "type": "string",
                    "description": "wave (default) | bfs | flow | pivot | rw | off",
                    "default": "wave",
                },
                "depth": {"type": "integer", "default": 2, "description": "Traversal depth"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
]


def schemas() -> dict[str, Any]:
    return {
        "deliberation_pack": DELIBERATION_PACK_SCHEMA,
        "mcp_tools": MCP_TOOLS,
    }


def write_schemas(out_dir: Path | str | None = None) -> dict[str, str]:
    """Write schema JSON files; returns written paths."""
    root = Path(out_dir) if out_dir else _SCHEMA_DIR
    root.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    pack_path = root / "deliberation_pack.schema.json"
    pack_path.write_text(json.dumps(DELIBERATION_PACK_SCHEMA, indent=2), encoding="utf-8")
    written["deliberation_pack"] = str(pack_path)
    tools_path = root / "mcp_tools.json"
    tools_path.write_text(json.dumps({"tools": MCP_TOOLS}, indent=2), encoding="utf-8")
    written["mcp_tools"] = str(tools_path)
    return written


def _type_ok(value: Any, expected: Any) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def _check(instance: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Minimal draft-ish validator (required + types + $defs refs for our packs)."""
    errors: list[str] = []
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref.startswith("#/$defs/"):
            name = ref.split("/")[-1]
            defs = schema.get("$defs") or {}
            # parent defs passed via closure — handled by caller embedding
            return errors
        return errors

    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_type_ok(instance, x) for x in types):
            errors.append(f"{path}: expected {t}, got {type(instance).__name__}")
            return errors

    if isinstance(instance, dict):
        for req in schema.get("required") or []:
            if req not in instance:
                errors.append(f"{path}: missing required '{req}'")
        props = schema.get("properties") or {}
        defs = schema.get("$defs") or {}
        for key, sub in props.items():
            if key not in instance:
                continue
            sub_schema = dict(sub)
            if "$ref" in sub_schema:
                ref = sub_schema["$ref"]
                if ref.startswith("#/$defs/"):
                    sub_schema = {**defs.get(ref.split("/")[-1], {}), "$defs": defs}
            elif sub_schema.get("type") == "array" and isinstance(sub_schema.get("items"), dict):
                items = dict(sub_schema["items"])
                if "$ref" in items and items["$ref"].startswith("#/$defs/"):
                    items = {**defs.get(items["$ref"].split("/")[-1], {}), "$defs": defs}
                for i, el in enumerate(instance[key] if isinstance(instance[key], list) else []):
                    errors.extend(_check(el, items, f"{path}.{key}[{i}]"))
                continue
            elif sub_schema.get("type") == "object":
                sub_schema = {**sub_schema, "$defs": defs}
            errors.extend(_check(instance[key], sub_schema, f"{path}.{key}"))
    return errors


def validate_deliberation_pack(pack: dict[str, Any]) -> list[str]:
    """Return list of validation errors (empty = ok)."""
    return _check(pack, DELIBERATION_PACK_SCHEMA)


def _default_report_path(repo: str) -> Path:
    p = Path(repo)
    if p.exists():
        return p / ".codeevolve" / "report.json"
    return Path.cwd() / ".codeevolve" / "report.json"


def _run_analyze(arguments: dict[str, Any]) -> dict[str, Any]:
    import os

    from codeevolve.api import CodeEvolve
    from codeevolve.provenance.ledger import build_provenance_ledger

    os.environ.setdefault("CODEEVOLVE_SKIP_HF", "1")
    os.environ.setdefault("CODEEVOLVE_SKIP_EMBED", "1")
    os.environ.setdefault("CODEEVOLVE_TAXONOMY_HEURISTIC", "1")
    os.environ.setdefault("CODEEVOLVE_SKIP_GHSA", "1")

    repo = str(arguments.get("repo") or "")
    if not repo:
        return {"error": "repo required"}
    max_commits = int(arguments.get("max_commits") or 200)
    out = Path(arguments["out"]) if arguments.get("out") else _default_report_path(repo)
    out.parent.mkdir(parents=True, exist_ok=True)

    report = CodeEvolve(repo).analyze(
        max_commits=max_commits,
        use_llm=False,
        ensure_slm=False,
        include_selection=bool(arguments.get("include_selection", False)),
        write_report=False,
        include_repo_report=False,
        include_hardware=False,
        include_cst=False,
        include_clones=False,
        include_reticulation=False,
        include_fork_lineage=False,
        include_semantic=False,
        include_rag=False,
    )
    data = report.to_dict()
    out.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    ledger = report.provenance or build_provenance_ledger(data)
    pack = ledger.deliberation_pack(path=arguments.get("path"))
    pack_out = arguments.get("pack_out")
    if pack_out:
        Path(pack_out).write_text(json.dumps(pack, indent=2, default=str), encoding="utf-8")
    return {
        "repo": report.repo,
        "report_path": str(out.resolve()),
        "pack_out": str(Path(pack_out).resolve()) if pack_out else None,
        "commit_count": report.commit_count,
        "dynamics_summary": (report.dynamics or {}).get("summary"),
        "stage": report.ecology.global_stage if report.ecology else None,
        "frame_ids": [f.id for f in ledger.frames[:12]],
        "pack": pack,
        "howto": (
            "Next: provenance_expand_frame / provenance_path_pack / provenance_resolve "
            f"with from_report={out}"
        ),
    }


def _run_evolve_toward_objective(arguments: dict[str, Any]) -> dict[str, Any]:
    from codeevolve.agent import run_agent
    from codeevolve.agent.objective import Objective

    repo = str(arguments.get("repo") or "")
    if not repo:
        return {"error": "repo required"}
    obj = Objective.parse(
        str(arguments.get("objective") or "follow_refactor"),
        path=arguments.get("path"),
        wave=arguments.get("wave"),
    )
    run = run_agent(
        repo,
        obj,
        max_rounds=int(arguments.get("max_rounds") or 1),
        apply=bool(arguments.get("apply", False)),
        llm=arguments.get("llm") or "auto",
        provider=arguments.get("provider"),
        model=arguments.get("model"),
        base_url=arguments.get("base_url"),
        api_key=arguments.get("api_key"),
        verify_cmd=arguments.get("verify_cmd"),
        max_commits=int(arguments.get("max_commits") or 200),
        path=arguments.get("path"),
        wave=arguments.get("wave"),
        model_tier=str(arguments.get("model_tier") or "slm"),
        cognition=bool(arguments.get("cognition", True)),
        spawn_subagents=bool(arguments.get("spawn_subagents", True)),
        allow_web=bool(arguments.get("allow_web", True)),
        allow_shell=bool(arguments.get("allow_shell", False)),
        rag_backend=str(arguments.get("rag_backend") or "memory"),
        max_subagents=int(arguments.get("max_subagents") or 3),
        use_worktree=bool(arguments.get("use_worktree", True)),
        approve=bool(arguments.get("approve", False)),
        auto_approve=bool(arguments.get("auto_approve", False)),
        max_wall_seconds=arguments.get("max_wall_seconds"),
        max_cost_usd=arguments.get("max_cost_usd"),
        run_tests_on_apply=bool(arguments.get("run_tests_on_apply", True)),
        parallel_subagents=bool(arguments.get("parallel_subagents", False)),
        resume=bool(arguments.get("resume", True)),
        previous_report=arguments.get("previous_report"),
        prefer_frames=bool(arguments.get("prefer_frames", True)),
        auto_widen_blast=bool(arguments.get("auto_widen_blast", True)),
        refuse_huge_blast=bool(arguments.get("refuse_huge_blast", True)),
        write_pr_review=bool(arguments.get("write_pr_review", True)),
    )
    payload = run.to_dict()
    out = arguments.get("out")
    if out:
        Path(out).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        payload["out"] = str(Path(out).resolve())
    payload["howto"] = (
        "Inspect rounds[].proposal (frame_ids, falsifier, edit_previews). "
        "Re-run with apply=true only after reviewing dry-run proposals. "
        "Prefer provenance_path_pack before large manual edits."
    )
    return payload


def dispatch_mcp_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute an MCP-shaped tool against a report path, live analyze, or inline report."""
    from codeevolve.provenance.ledger import build_provenance_ledger, query_provenance

    if name == "analyze_repo":
        return _run_analyze(arguments)
    if name == "evolve_toward_objective":
        return _run_evolve_toward_objective(arguments)
    if name == "agent_cognition_info":
        from codeevolve.agent.cognition import describe_cognition

        return describe_cognition()
    if name == "context_graph":
        from codeevolve.graph import query_context

        report = arguments.get("report")
        path = arguments.get("from_report")
        if report is None and path:
            report = json.loads(Path(path).read_text(encoding="utf-8"))
        if report is None and not arguments.get("from_agent"):
            guess = Path.cwd() / ".codeevolve" / "report.json"
            if guess.is_file():
                report = json.loads(guess.read_text(encoding="utf-8"))
        agent_dir = arguments.get("from_agent")
        if not agent_dir:
            guess_a = Path.cwd() / ".codeevolve" / "agent"
            if guess_a.is_dir() and ((guess_a / "run.json").is_file() or (guess_a / "cognition.json").is_file()):
                agent_dir = str(guess_a)
        if report is None and not agent_dir:
            return {
                "error": "from_report or from_agent required",
                "hint": "analyze_repo and/or evolve_toward_objective, then context_graph",
            }
        kinds = arguments.get("kind")
        if isinstance(kinds, str):
            kinds = [kinds]
        prev = arguments.get("previous")
        prev_report = None
        if isinstance(prev, str) and prev:
            prev_report = json.loads(Path(prev).read_text(encoding="utf-8"))
        elif isinstance(prev, dict):
            prev_report = prev
        return query_context(
            report=report if isinstance(report, dict) else None,
            agent_dir=agent_dir,
            previous=prev_report,
            search=arguments.get("search"),
            flow=arguments.get("flow") or False,
            kernel=arguments.get("kernel"),
            kinds=kinds,
            family=arguments.get("family"),
            pivot=arguments.get("pivot"),
            precedent=arguments.get("precedent") or False,
            delta=bool(arguments.get("delta")),
            surface=bool(arguments.get("surface")),
            traverse=arguments.get("traverse") if arguments.get("traverse") is not None else True,
            depth=int(arguments.get("depth") or 2),
            limit=int(arguments.get("limit") or 20),
        )
    if name == "spawn_kernel_subagents":
        from codeevolve.agent.kernel import decompose_objective
        from codeevolve.agent.objective import Objective
        from codeevolve.agent.subagents import spawn_subagents

        repo = str(arguments.get("repo") or "")
        if not repo:
            return {"error": "repo required"}
        obj = Objective.parse(
            str(arguments.get("objective") or "follow_refactor"),
            path=arguments.get("path"),
        )
        kernels = arguments.get("kernels")
        if not kernels:
            kernels = [k.name for k in decompose_objective(obj, max_kernels=int(arguments.get("max_agents") or 3))]
        results = spawn_subagents(
            repo,
            obj,
            list(kernels),
            max_agents=int(arguments.get("max_agents") or 3),
            allow_web=bool(arguments.get("allow_web", True)),
            llm="heuristic",
            parallel=bool(arguments.get("parallel", False)),
        )
        return {
            "repo": repo,
            "objective": obj.to_dict(),
            "subagents": [r.to_dict() for r in results],
            "count": len(results),
        }
    if name == "viz_phylogeny":
        from codeevolve.viz import build_model, write_viz

        report = arguments.get("report")
        if report is None:
            path = arguments.get("from_report")
            if not path:
                guess = Path.cwd() / ".codeevolve" / "report.json"
                if guess.is_file():
                    path = str(guess)
                else:
                    return {
                        "error": "from_report required (or run analyze_repo first)",
                        "hint": "analyze_repo → viz_phylogeny with from_report",
                    }
            report = json.loads(Path(path).read_text(encoding="utf-8"))
        out = str(arguments.get("out") or (Path.cwd() / ".codeevolve" / "viz.html"))
        written = write_viz(
            report,
            out,
            kind=str(arguments.get("kind") or "all"),
            fmt=str(arguments.get("format") or "html"),
            collapse_unary=bool(arguments.get("collapse_unary", False)),
        )
        model = build_model(report)
        return {
            "out": str(written),
            "kind": arguments.get("kind") or "all",
            "node_count": model.node_count,
            "truncated": model.truncated,
            "parsimony": model.parsimony.to_dict(),
        }

    report = arguments.get("report")
    if report is None:
        path = arguments.get("from_report")
        if not path:
            # convenience: default report location
            guess = Path.cwd() / ".codeevolve" / "report.json"
            if guess.is_file():
                path = str(guess)
            else:
                return {
                    "error": "from_report required (or run analyze_repo first)",
                    "hint": "analyze_repo → provenance_pack with from_report",
                }
        report = json.loads(Path(path).read_text(encoding="utf-8"))
    ledger = build_provenance_ledger(report)

    if name == "provenance_pack":
        return query_provenance(
            ledger,
            pack=True,
            path=arguments.get("path"),
            clade=arguments.get("clade"),
        )
    if name == "provenance_expand_frame":
        return query_provenance(ledger, frame=arguments.get("frame"))
    if name == "provenance_path_pack":
        return query_provenance(ledger, path_pack=arguments.get("path"))
    if name == "provenance_resolve":
        return query_provenance(
            ledger,
            resolve=arguments.get("resolve"),
            depth=int(arguments.get("depth") or 2),
        )
    if name == "provenance_timeline":
        return query_provenance(
            ledger,
            timeline=True,
            path=arguments.get("path"),
            clade=arguments.get("clade"),
        )
    return {"error": f"unknown tool: {name}", "tools": [t["name"] for t in MCP_TOOLS]}
