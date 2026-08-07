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


def dispatch_mcp_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute an MCP-shaped tool against a report path, live analyze, or inline report."""
    from codeevolve.provenance.ledger import build_provenance_ledger, query_provenance

    if name == "analyze_repo":
        return _run_analyze(arguments)

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
