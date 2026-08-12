"""Best-effort symbol phylogeny via regex (optional tree-sitter later)."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.gitlog import list_tracked_files

_PY_DEF = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_][\w]*)\s*\(", re.M)
_PY_CLASS = re.compile(r"^\s*class\s+([A-Za-z_][\w]*)\s*[\(:]", re.M)
_JS_FN = re.compile(
    r"(?:(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][\w]*))"
    r"|(?:(?:export\s+)?const\s+([A-Za-z_][\w]*)\s*=\s*(?:async\s*)?\()",
    re.M,
)
_JS_CLASS = re.compile(r"(?:export\s+)?class\s+([A-Za-z_][\w]*)", re.M)
_GO_FN = re.compile(r"^func\s+(?:\([^)]+\)\s*)?([A-Za-z_][\w]*)\s*\(", re.M)
_RS_FN = re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_][\w]*)\s*[<(]", re.M)


@dataclass
class SymbolNode:
    qualname: str
    kind: str  # function|class
    path: str
    line: int
    end_line: int | None = None  # precise when AST/tree-sitter available

    def to_dict(self) -> dict[str, Any]:
        return {
            "qualname": self.qualname,
            "kind": self.kind,
            "path": self.path,
            "line": self.line,
            "end_line": self.end_line,
        }


@dataclass
class SymbolReport:
    symbols: list[SymbolNode] = field(default_factory=list)
    by_path: dict[str, int] = field(default_factory=dict)
    kind_counts: dict[str, int] = field(default_factory=dict)
    engine: str = "regex"

    @property
    def symbol_count(self) -> int:
        return len(self.symbols)

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "symbol_count": self.symbol_count,
            "by_path": dict(list(self.by_path.items())[:80]),
            "kind_counts": dict(self.kind_counts),
            "symbols": [s.to_dict() for s in self.symbols[:400]],
        }


def _scan_text(path: str, text: str) -> list[SymbolNode]:
    ext = Path(path).suffix.lower()
    out: list[SymbolNode] = []
    if ext == ".py":
        for rx, kind in ((_PY_CLASS, "class"), (_PY_DEF, "function")):
            for m in rx.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                out.append(SymbolNode(f"{path}::{m.group(1)}", kind, path, line))
    elif ext in {".js", ".jsx", ".ts", ".tsx"}:
        for m in _JS_CLASS.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            out.append(SymbolNode(f"{path}::{m.group(1)}", "class", path, line))
        for m in _JS_FN.finditer(text):
            name = m.group(1) or m.group(2)
            if not name:
                continue
            line = text.count("\n", 0, m.start()) + 1
            out.append(SymbolNode(f"{path}::{name}", "function", path, line))
    elif ext == ".go":
        for m in _GO_FN.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            out.append(SymbolNode(f"{path}::{m.group(1)}", "function", path, line))
    elif ext == ".rs":
        for m in _RS_FN.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            out.append(SymbolNode(f"{path}::{m.group(1)}", "function", path, line))
    return out


def _scan_python_ast(path: str, text: str) -> list[SymbolNode] | None:
    """Stdlib AST scopes with accurate end_lineno (preferred for Python fences)."""
    import ast

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    out: list[SymbolNode] = []

    class V(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            out.append(
                SymbolNode(
                    f"{path}::{node.name}",
                    "function",
                    path,
                    int(node.lineno),
                    end_line=int(getattr(node, "end_lineno", None) or node.lineno),
                )
            )
            self.generic_visit(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            out.append(
                SymbolNode(
                    f"{path}::{node.name}",
                    "function",
                    path,
                    int(node.lineno),
                    end_line=int(getattr(node, "end_lineno", None) or node.lineno),
                )
            )
            self.generic_visit(node)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
            out.append(
                SymbolNode(
                    f"{path}::{node.name}",
                    "class",
                    path,
                    int(node.lineno),
                    end_line=int(getattr(node, "end_lineno", None) or node.lineno),
                )
            )
            self.generic_visit(node)

    V().visit(tree)
    return out


def _scan_python_treesitter(path: str, text: str) -> list[SymbolNode] | None:
    try:
        from tree_sitter_languages import get_parser  # type: ignore
    except Exception:
        return None
    try:
        parser = get_parser("python")
        tree = parser.parse(text.encode("utf-8"))
    except Exception:
        return None
    out: list[SymbolNode] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type in {"function_definition", "class_definition", "async_function_definition"}:
            name_node = node.child_by_field_name("name")
            if not name_node:
                continue
            name = text[name_node.start_byte : name_node.end_byte]
            kind = "class" if node.type == "class_definition" else "function"
            line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            out.append(SymbolNode(f"{path}::{name}", kind, path, line, end_line=end_line))
    return out


def _scan_js_ts_treesitter(path: str, text: str) -> list[SymbolNode] | None:
    try:
        from tree_sitter_languages import get_parser  # type: ignore
    except Exception:
        return None
    ext = Path(path).suffix.lower()
    lang = "tsx" if ext == ".tsx" else "typescript" if ext in {".ts", ".tsx"} else "javascript"
    try:
        parser = get_parser(lang)
        tree = parser.parse(text.encode("utf-8"))
    except Exception:
        # fallback language id
        try:
            parser = get_parser("javascript")
            tree = parser.parse(text.encode("utf-8"))
        except Exception:
            return None
    interesting = {
        "function_declaration",
        "class_declaration",
        "method_definition",
        "generator_function_declaration",
    }
    out: list[SymbolNode] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type not in interesting:
            continue
        name_node = node.child_by_field_name("name")
        if not name_node:
            continue
        name = text[name_node.start_byte : name_node.end_byte]
        kind = "class" if "class" in node.type else "function"
        out.append(
            SymbolNode(
                f"{path}::{name}",
                kind,
                path,
                node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
            )
        )
    return out or None


def scan_symbols(path: str, text: str) -> tuple[list[SymbolNode], str]:
    """Best-effort symbols with spans: ast → tree-sitter → regex."""
    ext = Path(path).suffix.lower()
    if ext == ".py":
        nodes = _scan_python_ast(path, text)
        if nodes:
            return nodes, "ast"
        nodes = _scan_python_treesitter(path, text)
        if nodes:
            return nodes, "tree_sitter"
    elif ext in {".js", ".jsx", ".ts", ".tsx"}:
        nodes = _scan_js_ts_treesitter(path, text)
        if nodes:
            return nodes, "tree_sitter"
    return _scan_text(path, text), "regex"


def extract_symbols(
    repo: Path | str,
    *,
    max_files: int = 400,
    paths: list[str] | None = None,
) -> SymbolReport:
    repo = Path(repo)
    engine = "regex"
    ts_ok = False
    try:
        from tree_sitter_languages import get_parser  # type: ignore  # noqa: F401

        ts_ok = True
        engine = "tree_sitter+regex"
    except Exception:
        pass

    files = paths or list_tracked_files(repo)
    files = [
        f
        for f in files
        if re.search(r"\.(py|js|jsx|ts|tsx|go|rs)$", f, re.I)
    ][:max_files]

    symbols: list[SymbolNode] = []
    by_path: dict[str, int] = defaultdict(int)
    kinds: dict[str, int] = defaultdict(int)
    for rel in files:
        p = repo / rel
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if len(text) > 1_500_000:
            continue
        found, eng = scan_symbols(rel, text)
        if eng != "regex":
            engine = eng if engine == "regex" else f"{eng}+regex"
        symbols.extend(found)
        by_path[rel] += len(found)
        for s in found:
            kinds[s.kind] += 1

    symbols.sort(key=lambda s: (s.path, s.line))
    return SymbolReport(
        symbols=symbols,
        by_path=dict(sorted(by_path.items(), key=lambda x: -x[1])),
        kind_counts=dict(kinds),
        engine=engine,
    )
