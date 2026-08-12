"""Write phylogeny viz artifacts (HTML gallery, SVG, JSON, Newick)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codeevolve.viz.builder import render_builder_page
from codeevolve.viz.html import SVG_KINDS, newick_of, render_gallery, scene_svg
from codeevolve.viz.model import VizModel, build_model

FORMATS = ("html", "svg", "json", "newick")


def write_viz(
    report: Any,
    path: Path | str,
    *,
    kind: str = "all",
    fmt: str = "html",
    collapse_unary: bool = False,
) -> Path:
    """Render phylogeny / 3D builder / clades / parsimony / gene-flow.

    ``path`` may be a file (``.html`` / ``.svg`` / ``.json`` / ``.nwk``) or a
    directory (writes gallery.html, builder.html, per-kind SVGs, tree.nwk, viz.json).
    """
    model = build_model(report)
    dest = Path(path)
    kind = (kind or "all").replace("_", "-")
    fmt = (fmt or "html").lower()
    if fmt == "nwk":
        fmt = "newick"

    if dest.suffix.lower() in {".html", ".svg", ".json", ".nwk", ".newick"}:
        dest.parent.mkdir(parents=True, exist_ok=True)
        _write_file(dest, model, kind=kind, fmt=_fmt_from_suffix(dest, fmt), collapse_unary=collapse_unary)
        return dest

    dest.mkdir(parents=True, exist_ok=True)
    (dest / "gallery.html").write_text(render_gallery(model, collapse_unary=collapse_unary), encoding="utf-8")
    (dest / "builder.html").write_text(render_builder_page(model), encoding="utf-8")
    wanted = list(SVG_KINDS) if kind in {"all", "", "3d"} else [k for k in [kind] if k in SVG_KINDS]
    for k in wanted:
        (dest / f"{k.replace('-', '_')}.svg").write_text(
            scene_svg(model, k, collapse_unary=collapse_unary),
            encoding="utf-8",
        )
    (dest / "tree.nwk").write_text(newick_of(model) + "\n", encoding="utf-8")
    (dest / "viz.json").write_text(json.dumps(model.to_dict(), indent=2, default=str), encoding="utf-8")
    return dest / ("builder.html" if kind in {"3d", "builder"} else "gallery.html")


def render_viz(
    report: Any,
    *,
    kind: str = "all",
    fmt: str = "html",
    collapse_unary: bool = False,
) -> str:
    model = build_model(report)
    kind = (kind or "all").replace("_", "-")
    fmt = (fmt or "html").lower()
    if fmt == "html" or kind == "all":
        if kind in {"3d", "builder"}:
            return render_builder_page(model)
        return render_gallery(model, collapse_unary=collapse_unary)
    if fmt == "json":
        return json.dumps(model.to_dict(), indent=2, default=str)
    if fmt in {"newick", "nwk"}:
        return newick_of(model)
    return scene_svg(model, kind if kind != "all" else "phylogeny", collapse_unary=collapse_unary)


def _fmt_from_suffix(path: Path, fallback: str) -> str:
    ext = path.suffix.lower()
    return {".html": "html", ".svg": "svg", ".json": "json", ".nwk": "newick", ".newick": "newick"}.get(ext, fallback)


def _write_file(path: Path, model: VizModel, *, kind: str, fmt: str, collapse_unary: bool) -> None:
    if fmt == "html":
        if kind in {"3d", "builder"}:
            path.write_text(render_builder_page(model), encoding="utf-8")
        else:
            path.write_text(render_gallery(model, collapse_unary=collapse_unary), encoding="utf-8")
        return
    if fmt == "json":
        path.write_text(json.dumps(model.to_dict(), indent=2, default=str), encoding="utf-8")
        return
    if fmt == "newick":
        path.write_text(newick_of(model) + "\n", encoding="utf-8")
        return
    k = kind if kind not in {"all", ""} else "phylogeny"
    path.write_text(scene_svg(model, k, collapse_unary=collapse_unary), encoding="utf-8")
