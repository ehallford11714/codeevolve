"""Tool registry — named callables the agent / subagents can invoke."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class ToolResult:
    ok: bool
    name: str
    output: Any
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "name": self.name,
            "output": self.output,
            "error": self.error,
            "meta": dict(self.meta),
        }


ToolFn = Callable[..., ToolResult]


@dataclass
class ToolSpec:
    name: str
    description: str
    fn: ToolFn
    schema: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "schema": dict(self.schema)}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def list(self) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self._tools.values()]

    def call(self, name: str, **kwargs: Any) -> ToolResult:
        spec = self._tools.get(name)
        if not spec:
            return ToolResult(ok=False, name=name, output=None, error=f"unknown tool: {name}")
        try:
            return spec.fn(**kwargs)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, name=name, output=None, error=str(exc))

    def names(self) -> list[str]:
        return sorted(self._tools)


def build_default_registry(
    repo: Path | str,
    *,
    allow_shell: bool = False,
    allow_web: bool = True,
    memory: Any = None,
    rag: Any = None,
) -> ToolRegistry:
    from codeevolve.agent.tools import files as file_tools
    from codeevolve.agent.tools import grep as grep_tools
    from codeevolve.agent.tools import web as web_tools
    from codeevolve.agent.tools import shell as shell_tools
    from codeevolve.agent.tools import codeevolve_tools as ce_tools
    from codeevolve.agent.tools import memory_tools

    root = Path(repo)
    reg = ToolRegistry()

    reg.register(
        ToolSpec(
            "file_read",
            "Read a UTF-8 text file under the repo (path-relative).",
            lambda path, max_chars=12000: file_tools.file_read(root, path, max_chars=max_chars),
            {"path": "string", "max_chars": "integer"},
        )
    )
    reg.register(
        ToolSpec(
            "file_list",
            "List files under a relative directory.",
            lambda path=".", glob="*", limit=80: file_tools.file_list(root, path, glob=glob, limit=limit),
            {"path": "string", "glob": "string", "limit": "integer"},
        )
    )
    reg.register(
        ToolSpec(
            "grep",
            "Ripgrep-like content search across the repo.",
            lambda pattern, path=".", glob="*", max_hits=40, ignore_case=True: grep_tools.grep(
                root, pattern, path=path, glob=glob, max_hits=max_hits, ignore_case=ignore_case
            ),
            {"pattern": "string", "path": "string", "glob": "string", "max_hits": "integer"},
        )
    )
    reg.register(
        ToolSpec(
            "rag_query",
            "Semantic RAG chunk retrieval over the codebase (in-memory by default).",
            lambda query, top_k=8: (
                ToolResult(
                    ok=True,
                    name="rag_query",
                    output=[h.to_dict() for h in rag.query(query, top_k=top_k)] if rag else [],
                    error=None if rag else "rag not configured",
                )
            ),
            {"query": "string", "top_k": "integer"},
        )
    )
    reg.register(
        ToolSpec(
            "morpheme_scan",
            "Extract morphological tokens / ontology hits for paths.",
            lambda paths=None: ce_tools.morpheme_scan(root, paths),
            {"paths": "array"},
        )
    )
    reg.register(
        ToolSpec(
            "memory_search",
            "Search in-memory agent notes.",
            lambda query, limit=12: memory_tools.memory_search(memory, query, limit=limit),
            {"query": "string", "limit": "integer"},
        )
    )
    reg.register(
        ToolSpec(
            "memory_add",
            "Add a note to agent memory.",
            lambda content, kind="working", tags=None: memory_tools.memory_add(
                memory, content, kind=kind, tags=tags
            ),
            {"content": "string", "kind": "string", "tags": "array"},
        )
    )
    reg.register(
        ToolSpec(
            "provenance_hint",
            "Load deliberation pack / path pack hints from report.json if present.",
            lambda path=None: ce_tools.provenance_hint(root, path=path),
            {"path": "string"},
        )
    )
    reg.register(
        ToolSpec(
            "graph_search",
            "Parse/search the context graph (families, pivots, agentic flow, precedent).",
            lambda query="", flow=False, kernel=None, limit=12, family=None, pivot=None, traverse="wave", precedent=False, depth=2: ce_tools.graph_search(
                root,
                query=query,
                flow=bool(flow),
                kernel=kernel,
                limit=limit,
                family=family,
                pivot=pivot,
                traverse=str(traverse or "wave"),
                precedent=precedent,
                depth=int(depth or 2),
            ),
            {
                "query": "string",
                "flow": "boolean",
                "kernel": "string",
                "limit": "integer",
                "family": "string",
                "pivot": "string",
                "traverse": "string",
                "precedent": "boolean",
                "depth": "integer",
            },
        )
    )
    if allow_web:
        reg.register(
            ToolSpec(
                "web_search",
                "Web search (DuckDuckGo HTML); returns titles/urls/snippets.",
                lambda query, max_results=5: web_tools.web_search(query, max_results=max_results),
                {"query": "string", "max_results": "integer"},
            )
        )
    if allow_shell:
        reg.register(
            ToolSpec(
                "shell",
                "Run a bounded shell command in the repo (explicitly enabled).",
                lambda command, timeout=60: shell_tools.shell_run(root, command, timeout=timeout),
                {"command": "string", "timeout": "integer"},
            )
        )
    return reg
