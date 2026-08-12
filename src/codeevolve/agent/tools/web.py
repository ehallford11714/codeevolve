"""Web search tool (DuckDuckGo HTML; degrades gracefully offline)."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from codeevolve.agent.tools.registry import ToolResult


def web_search(query: str, *, max_results: int = 5) -> ToolResult:
    if os.environ.get("CODEEVOLVE_DISABLE_WEB", "").lower() in {"1", "true", "yes"}:
        return ToolResult(ok=False, name="web_search", output=[], error="web disabled by env")

    q = (query or "").strip()
    if not q:
        return ToolResult(ok=False, name="web_search", output=[], error="empty query")

    # Prefer DDG instant answer API (JSON) — no key
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode(
        {"q": q, "format": "json", "no_html": 1, "skip_disambig": 1}
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "CodeEvolveAgent/0.18"})
        with urllib.request.urlopen(req, timeout=12) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return ToolResult(ok=False, name="web_search", output=[], error=f"search failed: {exc}")

    results: list[dict[str, str]] = []
    abstract = (data.get("AbstractText") or "").strip()
    abstract_url = (data.get("AbstractURL") or "").strip()
    if abstract:
        results.append(
            {
                "title": data.get("Heading") or q,
                "url": abstract_url,
                "snippet": abstract[:400],
            }
        )
    for topic in (data.get("RelatedTopics") or [])[: max_results * 2]:
        if not isinstance(topic, dict):
            continue
        if "Topics" in topic:
            for sub in topic.get("Topics") or []:
                if isinstance(sub, dict) and sub.get("Text"):
                    results.append(
                        {
                            "title": (sub.get("Text") or "")[:80],
                            "url": str(sub.get("FirstURL") or ""),
                            "snippet": str(sub.get("Text") or "")[:400],
                        }
                    )
        elif topic.get("Text"):
            results.append(
                {
                    "title": (topic.get("Text") or "")[:80],
                    "url": str(topic.get("FirstURL") or ""),
                    "snippet": str(topic.get("Text") or "")[:400],
                }
            )
        if len(results) >= max_results:
            break

    # Fallback scrape lite HTML if API sparse
    if len(results) < 1:
        html_url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": q})
        try:
            req = urllib.request.Request(html_url, headers={"User-Agent": "CodeEvolveAgent/0.18"})
            with urllib.request.urlopen(req, timeout=12) as resp:  # noqa: S310
                html = resp.read().decode("utf-8", errors="replace")
            for m in re.finditer(
                r'class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>',
                html,
                re.I | re.S,
            ):
                title = re.sub(r"<[^>]+>", "", m.group("title")).strip()
                results.append({"title": title[:120], "url": m.group("url"), "snippet": ""})
                if len(results) >= max_results:
                    break
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            pass

    return ToolResult(
        ok=True,
        name="web_search",
        output=results[:max_results],
        meta={"query": q, "count": len(results[:max_results])},
    )
