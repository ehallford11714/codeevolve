"""Compaction — compress traces, tool logs, and memory into durable summaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from codeevolve.agent.memory import AgentMemory


@dataclass
class CompactResult:
    summary: str
    kept_ids: list[str] = field(default_factory=list)
    dropped: int = 0
    bullets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "kept_ids": list(self.kept_ids),
            "dropped": self.dropped,
            "bullets": list(self.bullets),
        }


def compact_texts(texts: list[str], *, max_bullets: int = 12, max_chars: int = 2400) -> CompactResult:
    bullets: list[str] = []
    seen: set[str] = set()
    for t in texts:
        line = " ".join((t or "").strip().split())
        if not line:
            continue
        key = line[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        bullets.append(line[:280])
        if len(bullets) >= max_bullets:
            break
    summary = "\n".join(f"- {b}" for b in bullets)
    if len(summary) > max_chars:
        summary = summary[: max_chars - 20] + "\n- …"
    return CompactResult(summary=summary or "(nothing to compact)", bullets=bullets)


def _protected(item: Any) -> bool:
    tags = set(getattr(item, "tags", None) or [])
    if tags & {"overridden", "falsified", "reflexion"}:
        return True
    meta = getattr(item, "meta", None) or {}
    if str(meta.get("outcome") or "") == "overridden":
        return True
    content = str(getattr(item, "content", "") or "").lower()
    if "overridden" in content and getattr(item, "kind", "") in {"episodic", "reflection", "working"}:
        return True
    return False


def compact_memory(memory: AgentMemory, *, keep_working: int = 8) -> CompactResult:
    """Fold older working/tool memories into one semantic compact note."""
    working = memory.list(kind="working", limit=80)
    tools = memory.list(kind="tool", limit=80)
    episodic = memory.list(kind="episodic", limit=40)
    pool = working[keep_working:] + tools + episodic
    pool = [i for i in pool if not _protected(i)]
    if not pool:
        snap = memory.working_snapshot(limit=keep_working)
        kept = [i.id for i in working[:keep_working]] + [i.id for i in episodic if _protected(i)]
        return CompactResult(summary=snap, kept_ids=kept)

    texts = [f"{i.kind}: {i.content}" for i in pool]
    result = compact_texts(texts)
    result.dropped = len(pool)
    result.kept_ids = [i.id for i in working[:keep_working]] + [i.id for i in episodic if _protected(i)]
    memory.add(
        result.summary,
        kind="compact",
        tags=["compaction"],
        meta={"dropped": result.dropped},
        score=1.5,
    )
    memory.add(
        result.summary[:500],
        kind="semantic",
        tags=["compact_summary"],
        score=1.2,
    )
    # demote compacted items (never overridden / reflexion)
    for item in pool:
        item.score *= 0.35
        item.tags = list(set(item.tags + ["compacted"]))
    memory.save()
    return result


def compact_round_trace(trace: dict[str, Any]) -> CompactResult:
    bits: list[str] = []
    if trace.get("step_id"):
        bits.append(f"step={trace['step_id']} accepted={trace.get('accepted')}")
    for n in (trace.get("notes") or [])[:8]:
        bits.append(str(n))
    prop = trace.get("proposal") or {}
    if prop.get("rationale"):
        bits.append(str(prop["rationale"])[:240])
    if prop.get("stance"):
        bits.append(f"stance={prop['stance']}")
    for fr in (prop.get("frame_ids") or [])[:6]:
        bits.append(f"frame:{fr}")
    return compact_texts(bits, max_bullets=10)
