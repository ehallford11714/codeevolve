"""Sprint boundaries from GitHub milestones or synthetic calendar weeks."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from codeevolve.gitlog import CommitRecord
from codeevolve.psychology.rhythm import analyze_fatigue


@dataclass
class SprintWindow:
    id: str
    title: str
    start: str | None
    due: str | None
    commit_count: int = 0
    churn: int = 0
    source: str = "calendar"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "start": self.start,
            "due": self.due,
            "commit_count": self.commit_count,
            "churn": self.churn,
            "source": self.source,
        }


@dataclass
class SprintReport:
    sprints: list[SprintWindow] = field(default_factory=list)
    source: str = "calendar"
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "sprints": [s.to_dict() for s in self.sprints],
            "summary": self.summary,
        }


def _gh_get(url: str, token: str | None) -> Any:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "codeevolve"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def fetch_milestones(owner: str, repo: str, *, token: str | None = None) -> list[dict[str, Any]]:
    tok = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    url = (
        f"https://api.github.com/repos/{urllib.parse.quote(owner)}/"
        f"{urllib.parse.quote(repo)}/milestones?state=all&per_page=30"
    )
    try:
        data = _gh_get(url, tok)
        return data if isinstance(data, list) else []
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return []


def analyze_sprints(
    commits: list[CommitRecord],
    *,
    owner: str | None = None,
    repo: str | None = None,
) -> SprintReport:
    milestones: list[dict[str, Any]] = []
    if owner and repo:
        milestones = fetch_milestones(owner, repo)

    if milestones:
        windows: list[SprintWindow] = []
        for m in milestones[:20]:
            due = m.get("due_on")
            created = m.get("created_at")
            sw = SprintWindow(
                id=str(m.get("number")),
                title=str(m.get("title") or f"milestone-{m.get('number')}"),
                start=created,
                due=due,
                source="github_milestone",
            )
            # assign commits before due_on
            due_dt = None
            start_dt = None
            try:
                if due:
                    due_dt = datetime.fromisoformat(due.replace("Z", "+00:00"))
                if created:
                    start_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                pass
            for c in commits:
                ts = c.timestamp if c.timestamp.tzinfo else c.timestamp.replace(tzinfo=timezone.utc)
                if due_dt and ts > due_dt:
                    continue
                if start_dt and ts < start_dt:
                    continue
                sw.commit_count += 1
                sw.churn += c.insertions + c.deletions
            windows.append(sw)
        windows.sort(key=lambda w: w.due or "")
        return SprintReport(
            sprints=windows,
            source="github_milestone",
            summary=f"{len(windows)} GitHub milestones as sprint boundaries",
        )

    # Fallback: reuse weekly bins from fatigue
    fat = analyze_fatigue(commits)
    sprints = [
        SprintWindow(
            id=w["week"],
            title=w["week"],
            start=None,
            due=None,
            commit_count=int(w["commits"]),
            churn=int(w["churn"]),
            source="calendar_week",
        )
        for w in fat.weekly
    ]
    return SprintReport(
        sprints=sprints,
        source="calendar_week",
        summary=f"{len(sprints)} synthetic week sprints (no milestones)",
    )
