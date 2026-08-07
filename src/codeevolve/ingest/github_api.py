"""GitHub Issues / PRs as selection-pressure signals (REST API)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SelectionPressure:
    owner: str
    repo: str
    issues_sampled: int = 0
    prs_sampled: int = 0
    open_issues: int = 0
    closed_issues: int = 0
    reopened_like: int = 0
    label_counts: dict[str, int] = field(default_factory=dict)
    bug_label_rate: float = 0.0
    pr_merge_rate: float = 0.0
    pressure_score: float = 0.0
    recent_issues: list[dict[str, Any]] = field(default_factory=list)
    recent_prs: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "repo": self.repo,
            "issues_sampled": self.issues_sampled,
            "prs_sampled": self.prs_sampled,
            "open_issues": self.open_issues,
            "closed_issues": self.closed_issues,
            "reopened_like": self.reopened_like,
            "label_counts": dict(list(self.label_counts.items())[:40]),
            "bug_label_rate": self.bug_label_rate,
            "pr_merge_rate": self.pr_merge_rate,
            "pressure_score": self.pressure_score,
            "recent_issues": list(self.recent_issues[:25]),
            "recent_prs": list(self.recent_prs[:25]),
            "notes": list(self.notes),
        }


def _gh_get(url: str, token: str | None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "codeevolve",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def fetch_selection_pressure(
    owner: str,
    repo: str,
    *,
    max_issues: int = 50,
    max_prs: int = 30,
    token: str | None = None,
) -> SelectionPressure:
    tok = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    sp = SelectionPressure(owner=owner, repo=repo)
    base = f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}"

    try:
        issues = _gh_get(f"{base}/issues?state=all&per_page={max_issues}", tok)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        sp.notes.append(f"issues fetch failed: {exc}")
        return sp

    if not isinstance(issues, list):
        sp.notes.append("unexpected issues payload")
        return sp

    bugish = 0
    labeled = 0
    for item in issues:
        if "pull_request" in item:
            continue
        sp.issues_sampled += 1
        state = (item.get("state") or "").lower()
        if state == "open":
            sp.open_issues += 1
        else:
            sp.closed_issues += 1
        title = (item.get("title") or "").lower()
        body = (item.get("body") or "").lower()
        if "reopen" in title or "reopen" in body:
            sp.reopened_like += 1
        labels = item.get("labels") or []
        if labels:
            labeled += 1
        label_names: list[str] = []
        is_bug = False
        for lab in labels:
            name = (lab.get("name") if isinstance(lab, dict) else str(lab)).lower()
            label_names.append(name)
            sp.label_counts[name] = sp.label_counts.get(name, 0) + 1
            if any(k in name for k in ("bug", "defect", "crash", "regression")):
                bugish += 1
                is_bug = True
        if len(sp.recent_issues) < 25:
            sp.recent_issues.append(
                {
                    "number": item.get("number"),
                    "title": item.get("title"),
                    "state": state,
                    "created_at": item.get("created_at"),
                    "closed_at": item.get("closed_at"),
                    "labels": label_names[:12],
                    "epistemic": "stated",
                    "bug_like": is_bug,
                }
            )

    sp.bug_label_rate = round(bugish / max(1, sp.issues_sampled), 4)

    try:
        prs = _gh_get(f"{base}/pulls?state=all&per_page={max_prs}", tok)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        sp.notes.append(f"prs fetch failed: {exc}")
        prs = []

    merged = 0
    if isinstance(prs, list):
        for pr in prs:
            sp.prs_sampled += 1
            if pr.get("merged_at"):
                merged += 1
            if len(sp.recent_prs) < 25:
                sp.recent_prs.append(
                    {
                        "number": pr.get("number"),
                        "title": pr.get("title"),
                        "state": pr.get("state"),
                        "created_at": pr.get("created_at"),
                        "merged_at": pr.get("merged_at"),
                        "user": (pr.get("user") or {}).get("login"),
                        "epistemic": "stated",
                    }
                )
    sp.pr_merge_rate = round(merged / max(1, sp.prs_sampled), 4) if sp.prs_sampled else 0.0

    # Selection pressure: bugs + reopen-like + open backlog vs merge health
    backlog = sp.open_issues / max(1, sp.issues_sampled)
    sp.pressure_score = round(
        min(
            1.0,
            0.45 * sp.bug_label_rate
            + 0.25 * (sp.reopened_like / max(1, sp.issues_sampled))
            + 0.2 * backlog
            + 0.1 * (1.0 - sp.pr_merge_rate),
        ),
        4,
    )
    if not tok:
        sp.notes.append("unauthenticated GitHub API (rate-limited); set GITHUB_TOKEN for reliability")
    return sp
