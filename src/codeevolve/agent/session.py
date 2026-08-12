"""Cross-run session state: last report path, delta frame memory, resume hints."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codeevolve.agent.memory import AgentMemory


SESSION_NAME = "session.json"


@dataclass
class AgentSession:
    repo: str
    last_report_path: str | None = None
    last_run_path: str | None = None
    last_score: dict[str, Any] | None = None
    last_objective: dict[str, Any] | None = None
    last_diff: dict[str, Any] | None = None
    updated_at: float = field(default_factory=time.time)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "last_report_path": self.last_report_path,
            "last_run_path": self.last_run_path,
            "last_score": self.last_score,
            "last_objective": self.last_objective,
            "last_diff": self.last_diff,
            "updated_at": self.updated_at,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentSession":
        return cls(
            repo=str(data.get("repo") or ""),
            last_report_path=data.get("last_report_path"),
            last_run_path=data.get("last_run_path"),
            last_score=data.get("last_score"),
            last_objective=data.get("last_objective"),
            last_diff=data.get("last_diff"),
            updated_at=float(data.get("updated_at") or time.time()),
            notes=list(data.get("notes") or []),
        )


def session_path(work_dir: Path | str) -> Path:
    return Path(work_dir) / SESSION_NAME


def load_session(work_dir: Path | str) -> AgentSession | None:
    path = session_path(work_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AgentSession.from_dict(data)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def save_session(work_dir: Path | str, session: AgentSession) -> Path:
    path = session_path(work_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    session.updated_at = time.time()
    path.write_text(json.dumps(session.to_dict(), indent=2, default=str), encoding="utf-8")
    return path


def previous_report_for_run(
    work_dir: Path | str,
    *,
    explicit: Path | str | None = None,
    resume: bool = True,
) -> Path | None:
    """Resolve previous report: explicit path wins, else session last_report."""
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    if not resume:
        return None
    sess = load_session(work_dir)
    if not sess or not sess.last_report_path:
        return None
    p = Path(sess.last_report_path)
    return p if p.is_file() else None


def remember_delta(
    memory: AgentMemory | None,
    *,
    report: dict[str, Any],
    previous_path: str | None,
    diff: dict[str, Any] | None,
    accepted: bool | None = None,
    frame_ids: list[str] | None = None,
) -> None:
    """Persist frame:delta:report style note into agent memory."""
    if memory is None:
        return
    improved = list((diff or {}).get("improved") or [])
    worsened = list((diff or {}).get("worsened") or [])
    frames = []
    for f in (report.get("provenance") or {}).get("frames") or []:
        fid = str(f.get("id") or "")
        if fid == "frame:delta:report" or fid.startswith("frame:delta"):
            frames.append(fid)
    if frame_ids:
        frames.extend(frame_ids)
    frames = list(dict.fromkeys(frames))
    decision = "n/a" if accepted is None else ("accepted" if accepted else "rejected")
    content = (
        f"delta memory: decision={decision} "
        f"improved={improved[:4]} worsened={worsened[:4]} "
        f"frames={frames[:4]} previous={previous_path}"
    )
    memory.add(
        content,
        kind="episodic",
        tags=["delta", "frame:delta:report", decision],
        meta={
            "improved": improved,
            "worsened": worsened,
            "frames": frames,
            "previous": previous_path,
            "accepted": accepted,
        },
        score=1.4,
    )


def update_session_after_run(
    work_dir: Path | str,
    *,
    repo: str,
    report_path: str | None,
    run_path: str | None,
    score: dict[str, Any] | None,
    objective: dict[str, Any] | None,
    diff: dict[str, Any] | None = None,
    notes: list[str] | None = None,
) -> AgentSession:
    sess = load_session(work_dir) or AgentSession(repo=repo)
    sess.repo = repo
    if report_path:
        sess.last_report_path = report_path
    if run_path:
        sess.last_run_path = run_path
    if score is not None:
        sess.last_score = score
    if objective is not None:
        sess.last_objective = objective
    if diff is not None:
        sess.last_diff = diff
    if notes:
        sess.notes = (sess.notes + list(notes))[-40:]
    save_session(work_dir, sess)
    return sess
