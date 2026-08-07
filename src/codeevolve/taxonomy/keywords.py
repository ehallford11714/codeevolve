"""Deep hierarchical keyword library for code-type classification.

Parses path / identifier / commit tokens against a nested ontology so taxonomy
breakouts can split mixed directories by what was actually built.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from codeevolve.embeddings import tokenize

# path → tokens: dirs, stem, camel/snake splits
_SPLIT = re.compile(r"[/\\._\-\s]+|(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

# ---------------------------------------------------------------------------
# Ontology: domain → family → kind → specialty
# Each node: keywords (path/content hits), weight boost for leaf matches
# ---------------------------------------------------------------------------

CODE_TYPE_ONTOLOGY: dict[str, Any] = {
    "architecture": {
        "_kw": ("src", "lib", "pkg", "app", "core", "modules", "internal"),
        "api": {
            "_kw": ("api", "apis", "endpoint", "endpoints", "routes", "routing", "router"),
            "rest": {"_kw": ("rest", "http", "https", "fastapi", "flask", "express", "django", "resource")},
            "graphql": {"_kw": ("graphql", "gql", "resolver", "schema", "mutation", "subscription")},
            "rpc": {"_kw": ("grpc", "protobuf", "proto", "rpc", "thrift", "avro")},
            "websocket": {"_kw": ("websocket", "ws", "socketio", "realtime", "sse")},
            "handler": {"_kw": ("handler", "handlers", "controller", "controllers", "viewset")},
            "middleware": {"_kw": ("middleware", "interceptor", "filter", "guard", "pipeline")},
            "client": {"_kw": ("client", "sdk", "sdkclient", "httpclient", "apiclient")},
        },
        "data": {
            "_kw": ("data", "db", "database", "persistence", "storage"),
            "model": {"_kw": ("model", "models", "entity", "entities", "schema", "dto", "types")},
            "repository": {"_kw": ("repo", "repository", "repositories", "dao", "store", "mapper")},
            "migration": {"_kw": ("migration", "migrations", "alembic", "flyway", "liquibase", "schema")},
            "query": {"_kw": ("query", "queries", "sql", "orm", "prisma", "sequelize", "sqlalchemy")},
            "cache": {"_kw": ("cache", "redis", "memcached", "lru")},
            "queue": {"_kw": ("queue", "broker", "kafka", "rabbit", "sqs", "pubsub", "celery", "worker")},
        },
        "ui": {
            "_kw": ("ui", "frontend", "web", "client", "views", "pages", "templates"),
            "component": {"_kw": ("component", "components", "widget", "widgets")},
            "page": {"_kw": ("page", "pages", "screen", "screens", "route", "view")},
            "style": {"_kw": ("css", "scss", "sass", "less", "stylesheet", "theme", "tailwind")},
            "state": {"_kw": ("redux", "zustand", "mobx", "store", "recoil", "context", "hooks")},
            "assets": {"_kw": ("assets", "static", "public", "images", "icons", "fonts")},
        },
        "domain": {
            "_kw": ("domain", "business", "service", "services", "usecase", "application"),
            "service": {"_kw": ("service", "services", "manager", "facade")},
            "policy": {"_kw": ("policy", "policies", "rules", "ruleengine")},
            "workflow": {"_kw": ("workflow", "workflows", "pipeline", "orchestrat", "saga")},
            "event": {"_kw": ("event", "events", "emitter", "listener", "pubsub", "bus")},
        },
        "security": {
            "_kw": ("security", "secure", "auth", "crypto", "iam"),
            "authn": {"_kw": ("auth", "authentication", "login", "oauth", "oidc", "jwt", "session", "passport")},
            "authz": {"_kw": ("authz", "authorization", "rbac", "acl", "permission", "roles", "policy")},
            "crypto": {"_kw": ("crypto", "encrypt", "decrypt", "hash", "tls", "ssl", "keystore")},
            "secrets": {"_kw": ("secret", "secrets", "vault", "credentials", "keypair")},
        },
        "infra": {
            "_kw": ("infra", "ops", "deploy", "platform", "sre"),
            "ci": {"_kw": ("ci", "cd", "github", "gitlab", "jenkins", "workflow", "actions", "pipeline")},
            "deploy": {"_kw": ("deploy", "deployment", "k8s", "kubernetes", "helm", "terraform", "pulumi", "docker", "compose")},
            "observability": {"_kw": ("observability", "metrics", "tracing", "otel", "prometheus", "grafana", "logging", "sentry")},
            "config": {"_kw": ("config", "configs", "settings", "env", "toml", "yaml", "yml")},
        },
        "ml": {
            "_kw": ("ml", "ai", "model", "models", "training", "inference", "llm", "embed"),
            "training": {"_kw": ("train", "training", "finetune", "dataset", "dataloader")},
            "inference": {"_kw": ("infer", "inference", "predict", "serving", "onnx")},
            "embeddings": {"_kw": ("embed", "embedding", "embeddings", "vector", "minilm", "word2vec")},
            "eval": {"_kw": ("eval", "evaluate", "benchmark", "scorecard", "metric")},
        },
    },
    "verification": {
        "_kw": ("test", "tests", "spec", "specs", "testing", "__tests__", "qa"),
        "unit": {"_kw": ("unit", "unittest", "pytest", "jest", "vitest", "_test", ".test.", ".spec.")},
        "integration": {"_kw": ("integration", "integ", "apitest")},
        "e2e": {"_kw": ("e2e", "endtoend", "playwright", "cypress", "selenium")},
        "fixture": {"_kw": ("fixture", "fixtures", "factory", "factories", "mock", "mocks", "stub", "fakes")},
        "benchmark": {"_kw": ("bench", "benchmark", "perf", "loadtest")},
    },
    "knowledge": {
        "_kw": ("docs", "doc", "documentation", "readme", "changelog", "adr"),
        "guide": {"_kw": ("guide", "tutorial", "howto", "gettingstarted")},
        "api_docs": {"_kw": ("openapi", "swagger", "redoc", "apidoc")},
        "architecture": {"_kw": ("architecture", "adr", "rfc", "design")},
        "changelog": {"_kw": ("changelog", "release", "notes", "history")},
    },
    "tooling": {
        "_kw": ("scripts", "tools", "tooling", "bin", "Makefile", "build"),
        "build": {"_kw": ("build", "webpack", "vite", "rollup", "esbuild", "gradle", "maven", "cargo", "cmake")},
        "lint": {"_kw": ("lint", "eslint", "ruff", "flake8", "prettier", "fmt", "format")},
        "codegen": {"_kw": ("codegen", "generate", "generator", "scaffold", "template")},
        "scripts": {"_kw": ("script", "scripts", "cli", "bin", "makefile")},
    },
    "utility": {
        "_kw": ("util", "utils", "helpers", "common", "shared", "lib", "misc"),
        "parsing": {"_kw": ("parse", "parser", "parsing", "lexer", "tokenize", "ast")},
        "serialize": {"_kw": ("serialize", "json", "yaml", "codec", "marshal", "pickle")},
        "time": {"_kw": ("time", "date", "datetime", "clock", "schedule", "cron")},
        "io": {"_kw": ("io", "fs", "filesystem", "path", "stream", "buffer")},
    },
}

# Extension → soft type hints (applied as weak evidence)
_EXT_HINTS: dict[str, tuple[str, ...]] = {
    ".py": ("architecture",),
    ".ts": ("architecture", "ui"),
    ".tsx": ("architecture", "ui", "component"),
    ".jsx": ("architecture", "ui", "component"),
    ".js": ("architecture",),
    ".go": ("architecture",),
    ".rs": ("architecture",),
    ".java": ("architecture",),
    ".kt": ("architecture",),
    ".css": ("architecture", "ui", "style"),
    ".scss": ("architecture", "ui", "style"),
    ".md": ("knowledge",),
    ".rst": ("knowledge",),
    ".yml": ("architecture", "infra", "config"),
    ".yaml": ("architecture", "infra", "config"),
    ".toml": ("architecture", "infra", "config"),
    ".json": ("architecture", "infra", "config"),
    ".proto": ("architecture", "api", "rpc"),
    ".sql": ("architecture", "data", "query"),
    ".tf": ("architecture", "infra", "deploy"),
}


@dataclass
class CodeTypeHit:
    path: str
    type_path: list[str]
    confidence: float
    matched: list[str] = field(default_factory=list)
    layer_hint: str = "other"

    @property
    def type_key(self) -> str:
        return "/".join(self.type_path) if self.type_path else "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "type_path": list(self.type_path),
            "type_key": self.type_key,
            "confidence": self.confidence,
            "matched": list(self.matched[:16]),
            "layer_hint": self.layer_hint,
        }


@dataclass
class HierarchyNode:
    name: str
    count: int = 0
    churn: int = 0
    confidence_sum: float = 0.0
    sample_paths: list[str] = field(default_factory=list)
    children: dict[str, "HierarchyNode"] = field(default_factory=dict)
    ecology_stage: str = ""
    trend_note: str = ""

    def to_dict(self, *, max_depth: int = 8, depth: int = 0) -> dict[str, Any]:
        if depth >= max_depth:
            return {"name": self.name, "count": self.count, "churn": self.churn}
        kids = sorted(self.children.values(), key=lambda n: (-n.count, n.name))
        return {
            "name": self.name,
            "count": self.count,
            "churn": self.churn,
            "mean_confidence": round(self.confidence_sum / max(1, self.count), 3),
            "ecology_stage": self.ecology_stage or None,
            "trend_note": self.trend_note or None,
            "sample_paths": list(self.sample_paths[:6]),
            "children": [c.to_dict(max_depth=max_depth, depth=depth + 1) for c in kids],
        }

@dataclass
class KeywordTaxonomyReport:
    hierarchy: HierarchyNode
    path_types: dict[str, CodeTypeHit]
    type_counts: dict[str, int]
    family_counts: dict[str, int]
    breakout_seeds: dict[str, str]
    summary: str = ""
    ontology_depth: int = 4

    def to_dict(self) -> dict[str, Any]:
        return {
            "hierarchy": self.hierarchy.to_dict(),
            "path_types": {k: v.to_dict() for k, v in list(self.path_types.items())[:400]},
            "type_counts": dict(list(self.type_counts.items())[:80]),
            "family_counts": dict(self.family_counts),
            "breakout_seeds": dict(list(self.breakout_seeds.items())[:200]),
            "ontology_depth": self.ontology_depth,
            "summary": self.summary,
            "ascii_tree": render_tree(self.hierarchy, max_depth=5),
        }


def path_keywords(path: str) -> list[str]:
    """Tokenize a file path into classification keywords."""
    norm = path.replace("\\", "/")
    parts = [p for p in _SPLIT.split(norm) if p]
    toks: list[str] = []
    for p in parts:
        low = p.lower()
        if len(low) >= 2 and not low.isdigit():
            toks.append(low)
        toks.extend(tokenize(p))
    # de-dupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for t in toks:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _walk_scores(
    node: dict[str, Any],
    tokens: set[str],
    path: list[str],
    scores: list[tuple[list[str], float, list[str]]],
) -> None:
    kw = tuple(node.get("_kw") or ())
    hits = [k for k in kw if k.lower() in tokens or any(k.lower() in t for t in tokens if len(k) >= 4)]
    # exact token match preferred
    exact = [k for k in kw if k.lower() in tokens]
    score = 0.0
    if exact:
        score += 1.0 + 0.35 * (len(exact) - 1)
    elif hits:
        score += 0.45 + 0.1 * (len(hits) - 1)
    child_keys = [k for k in node if not k.startswith("_")]
    if score > 0 or not path:
        # explore children even on weak root
        pass
    if not child_keys:
        if score > 0 and path:
            scores.append((list(path), score, exact or hits))
        return
    progressed = False
    for name in child_keys:
        child = node[name]
        if not isinstance(child, dict):
            continue
        child_path = path + [name]
        before = len(scores)
        _walk_scores(child, tokens, child_path, scores)
        if len(scores) > before:
            progressed = True
            # boost parent contribution onto best child of this branch
            if score > 0:
                tp, sc, mt = scores[-1]
                scores[-1] = (tp, sc + score * 0.35, list(dict.fromkeys((exact or hits) + mt)))
    if score > 0 and path and not progressed:
        scores.append((list(path), score, exact or hits))


def _layer_hint(type_path: list[str]) -> str:
    if not type_path:
        return "other"
    root = type_path[0]
    if root == "verification":
        return "tests"
    if root == "knowledge":
        return "docs"
    if root == "tooling":
        return "config" if "build" in type_path or "lint" in type_path else "utility"
    if root == "utility":
        return "utility"
    if "infra" in type_path and "config" in type_path:
        return "config"
    if "infra" in type_path and "ci" in type_path:
        return "config"
    return "core"


def _path_segment_tokens(path: str) -> set[str]:
    """Directory segments only (strong structural signal)."""
    norm = path.replace("\\", "/").lower()
    parts = norm.split("/")
    dirs = parts[:-1] if len(parts) > 1 else parts
    out: set[str] = set()
    for d in dirs:
        for t in _SPLIT.split(d):
            if len(t) >= 2 and not t.isdigit():
                out.add(t)
    return out


def classify_path(path: str, *, extra_tokens: Iterable[str] | None = None) -> CodeTypeHit:
    """Classify a single path into a deep type hierarchy."""
    toks = path_keywords(path)
    if extra_tokens:
        toks = list(dict.fromkeys(toks + [t.lower() for t in extra_tokens if t]))
    token_set = set(toks)
    dir_tokens = _path_segment_tokens(path)
    # extension soft hints
    ext = ""
    if "." in path.replace("\\", "/").split("/")[-1]:
        ext = "." + path.replace("\\", "/").split("/")[-1].rsplit(".", 1)[-1].lower()
    for hint in _EXT_HINTS.get(ext, ()):
        token_set.add(hint.lower())

    scores: list[tuple[list[str], float, list[str]]] = []
    for root_name, root_node in CODE_TYPE_ONTOLOGY.items():
        if not isinstance(root_node, dict):
            continue
        _walk_scores(root_node, token_set, [root_name], scores)

    if not scores:
        return CodeTypeHit(path=path, type_path=["unknown"], confidence=0.15, matched=[], layer_hint="other")

    # Boost branches whose keywords appear as directory segments
    boosted: list[tuple[list[str], float, list[str]]] = []
    for tp, sc, mt in scores:
        bonus = 0.0
        for m in mt:
            if m.lower() in dir_tokens:
                bonus += 0.85
        # also credit ontology node names present as dirs
        for part in tp:
            if part.lower() in dir_tokens:
                bonus += 0.55
        boosted.append((tp, sc + bonus, mt))

    boosted.sort(key=lambda x: (-x[1], -len(x[0])))
    best_path, best_score, matched = boosted[0]
    # normalize confidence roughly into 0..1
    conf = min(0.98, best_score / (best_score + 1.8))
    if len(best_path) >= 3:
        conf = min(0.99, conf + 0.08)
    return CodeTypeHit(
        path=path,
        type_path=best_path,
        confidence=round(conf, 3),
        matched=[m.lower() for m in matched[:16]],
        layer_hint=_layer_hint(best_path),
    )


def classify_paths(
    paths: Iterable[str],
    *,
    path_extra: dict[str, Iterable[str]] | None = None,
) -> dict[str, CodeTypeHit]:
    out: dict[str, CodeTypeHit] = {}
    for p in paths:
        extra = path_extra.get(p) if path_extra else None
        out[p] = classify_path(p, extra_tokens=extra)
    return out


def build_type_hierarchy(
    path_types: dict[str, CodeTypeHit],
    *,
    churn_by_path: dict[str, int] | None = None,
) -> HierarchyNode:
    root = HierarchyNode(name="built")
    churn_by_path = churn_by_path or {}
    for path, hit in path_types.items():
        node = root
        node.count += 1
        node.churn += churn_by_path.get(path, 0)
        node.confidence_sum += hit.confidence
        for part in hit.type_path:
            if part not in node.children:
                node.children[part] = HierarchyNode(name=part)
            node = node.children[part]
            node.count += 1
            node.churn += churn_by_path.get(path, 0)
            node.confidence_sum += hit.confidence
            if len(node.sample_paths) < 8 and path not in node.sample_paths:
                node.sample_paths.append(path)
    return root


def breakout_seed_for_path(path: str, hit: CodeTypeHit, *, min_confidence: float = 0.42) -> str:
    """Seed key for taxonomic breakouts: type lineage when confident, else top dir."""
    top = path.replace("\\", "/").split("/")[0] if "/" in path.replace("\\", "/") or "\\" in path else "(root)"
    if hit.confidence < min_confidence or not hit.type_path or hit.type_path == ["unknown"]:
        return f"dir:{top}"
    # Use 2–3 levels for split granularity
    depth = 3 if hit.confidence >= 0.55 else 2
    key = "/".join(hit.type_path[:depth])
    return f"type:{key}|dir:{top}"


def compute_breakout_seeds(path_types: dict[str, CodeTypeHit]) -> dict[str, str]:
    return {p: breakout_seed_for_path(p, h) for p, h in path_types.items()}


def render_tree(node: HierarchyNode, *, max_depth: int = 5) -> str:
    """ASCII nested tree of what was built."""
    lines: list[str] = []

    def walk(n: HierarchyNode, prefix: str, depth: int, is_last: bool) -> None:
        connector = "" if depth == 0 else ("└─ " if is_last else "├─ ")
        bits = [f"{n.name}", f"n={n.count}"]
        if n.churn:
            bits.append(f"churn={n.churn}")
        if n.ecology_stage:
            bits.append(n.ecology_stage)
        if n.trend_note:
            bits.append(n.trend_note)
        lines.append(f"{prefix}{connector}{' · '.join(bits)}")
        if depth >= max_depth:
            return
        kids = sorted(n.children.values(), key=lambda x: (-x.count, x.name))
        for i, child in enumerate(kids):
            last = i == len(kids) - 1
            extension = "" if depth == 0 else ("   " if is_last else "│  ")
            walk(child, prefix + extension, depth + 1, last)

    walk(node, "", 0, True)
    return "\n".join(lines)


def annotate_hierarchy_ecology(
    hierarchy: HierarchyNode,
    *,
    path_to_clade: dict[str, str] | None = None,
    clade_stages: dict[str, str] | None = None,
    path_types: dict[str, CodeTypeHit] | None = None,
) -> None:
    """Attach dominant ecological stage notes onto hierarchy nodes."""
    if not clade_stages or not path_to_clade or not path_types:
        return

    def walk(node: HierarchyNode, type_prefix: list[str]) -> None:
        stage_votes: Counter[str] = Counter()
        for path, hit in path_types.items():
            if hit.type_path[: len(type_prefix)] != type_prefix:
                continue
            cid = path_to_clade.get(path)
            if cid and cid in clade_stages:
                stage_votes[clade_stages[cid]] += 1
        if stage_votes:
            stage, n = stage_votes.most_common(1)[0]
            node.ecology_stage = stage
            total = sum(stage_votes.values())
            node.trend_note = f"{stage} ({n}/{total} files)"
        for name, child in node.children.items():
            walk(child, type_prefix + [name])

    for name, child in hierarchy.children.items():
        walk(child, [name])


def analyze_keyword_taxonomy(
    paths: Iterable[str],
    *,
    churn_by_path: dict[str, int] | None = None,
    path_extra: dict[str, Iterable[str]] | None = None,
) -> KeywordTaxonomyReport:
    path_list = list(paths)
    path_types = classify_paths(path_list, path_extra=path_extra)
    hierarchy = build_type_hierarchy(path_types, churn_by_path=churn_by_path)
    type_counts: dict[str, int] = defaultdict(int)
    family_counts: dict[str, int] = defaultdict(int)
    for hit in path_types.values():
        type_counts[hit.type_key] += 1
        if hit.type_path:
            family_counts[hit.type_path[0]] += 1
    seeds = compute_breakout_seeds(path_types)
    top = ", ".join(f"{k}:{v}" for k, v in sorted(type_counts.items(), key=lambda x: -x[1])[:6])
    return KeywordTaxonomyReport(
        hierarchy=hierarchy,
        path_types=path_types,
        type_counts=dict(sorted(type_counts.items(), key=lambda x: -x[1])),
        family_counts=dict(sorted(family_counts.items(), key=lambda x: -x[1])),
        breakout_seeds=seeds,
        summary=f"Classified {len(path_list)} paths into deep type hierarchy; top={top}",
    )


def ontology_outline(*, max_depth: int = 4) -> dict[str, Any]:
    """Return the static ontology tree (for docs / CLI)."""

    def walk(node: dict[str, Any], depth: int) -> dict[str, Any]:
        kids = {}
        if depth < max_depth:
            for k, v in node.items():
                if k.startswith("_") or not isinstance(v, dict):
                    continue
                kids[k] = walk(v, depth + 1)
        return {"keywords": list(node.get("_kw") or [])[:12], "children": kids}

    return {name: walk(node, 1) for name, node in CODE_TYPE_ONTOLOGY.items()}
