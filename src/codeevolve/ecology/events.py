"""Lifecycle event corpus: tags/releases, semver majors, revert storms, optional GHSA."""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from codeevolve.gitlog import CommitRecord

EventKind = Literal[
    "release",
    "major_release",
    "minor_release",
    "patch_release",
    "security",
    "revert_storm",
    "pioneer_window",
]

_SEMVER = re.compile(
    r"v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)",
    re.I,
)
_SEC_TAG = re.compile(r"(security|cve|ghsa|advisory|heartbleed)", re.I)


@dataclass
class LifecycleEvent:
    kind: EventKind
    when: datetime
    label: str
    stage_hint: str  # pioneer|growth|disturbance|consolidation|maturity|decline
    confidence: float = 0.7
    source: str = "git"
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "when": self.when.isoformat(),
            "label": self.label,
            "stage_hint": self.stage_hint,
            "confidence": self.confidence,
            "source": self.source,
            "meta": dict(self.meta),
        }


@dataclass
class EventCorpus:
    events: list[LifecycleEvent] = field(default_factory=list)
    tags_seen: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_count": len(self.events),
            "tags_seen": self.tags_seen,
            "by_kind": _count_kinds(self.events),
            "events": [e.to_dict() for e in self.events[:80]],
            "notes": list(self.notes),
        }


def _count_kinds(events: list[LifecycleEvent]) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in events:
        out[e.kind] = out.get(e.kind, 0) + 1
    return out


def _run_git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        return ""
    return r.stdout or ""


def _parse_ts(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        # git %cI / %aI
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return datetime.fromisoformat(raw)
    except ValueError:
        pass
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    except (ValueError, OSError):
        return None


def list_tag_events(repo: Path | str, *, max_tags: int = 80) -> list[LifecycleEvent]:
    repo = Path(repo)
    # tag|date|subject
    out = _run_git(
        repo,
        "for-each-ref",
        "--sort=-creatordate",
        "--format=%(refname:short)|%(creatordate:iso-strict)|%(subject)",
        "refs/tags",
    )
    events: list[LifecycleEvent] = []
    for line in out.splitlines()[:max_tags]:
        parts = line.split("|", 2)
        if len(parts) < 2:
            continue
        tag, ts_raw = parts[0].strip(), parts[1].strip()
        subject = parts[2].strip() if len(parts) > 2 else ""
        when = _parse_ts(ts_raw)
        if not when or not tag:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        kind: EventKind = "release"
        hint = "consolidation"
        conf = 0.55
        m = _SEMVER.search(tag)
        if m:
            major, minor, patch = int(m.group("major")), int(m.group("minor")), int(m.group("patch"))
            if major >= 1 and minor == 0 and patch == 0:
                kind, hint, conf = "major_release", "growth", 0.85
            elif patch == 0 and minor > 0:
                kind, hint, conf = "minor_release", "growth", 0.75
            elif patch > 0:
                kind, hint, conf = "patch_release", "maturity", 0.65
            else:
                kind, hint, conf = "release", "consolidation", 0.6
        blob = f"{tag} {subject}"
        if _SEC_TAG.search(blob):
            kind, hint, conf = "security", "disturbance", 0.9
        events.append(
            LifecycleEvent(
                kind=kind,
                when=when,
                label=tag,
                stage_hint=hint,
                confidence=conf,
                source="git-tag",
                meta={"subject": subject[:120]},
            )
        )
    return events


def revert_storm_events(
    commits: list[CommitRecord],
    *,
    window_days: int = 14,
    min_reverts: int = 3,
) -> list[LifecycleEvent]:
    reverts = sorted([c for c in commits if c.is_revert], key=lambda c: c.timestamp)
    if not reverts:
        return []
    events: list[LifecycleEvent] = []
    i = 0
    while i < len(reverts):
        start = reverts[i].timestamp
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        j = i
        while j < len(reverts):
            t = reverts[j].timestamp
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if (t - start) > timedelta(days=window_days):
                break
            j += 1
        cluster = reverts[i:j]
        if len(cluster) >= min_reverts:
            mid = cluster[len(cluster) // 2].timestamp
            if mid.tzinfo is None:
                mid = mid.replace(tzinfo=timezone.utc)
            events.append(
                LifecycleEvent(
                    kind="revert_storm",
                    when=mid,
                    label=f"revert_storm_n={len(cluster)}",
                    stage_hint="disturbance",
                    confidence=min(0.95, 0.55 + 0.05 * len(cluster)),
                    source="git-reverts",
                    meta={"count": len(cluster), "window_days": window_days},
                )
            )
            i = j
        else:
            i += 1
    return events


def pioneer_event(commits: list[CommitRecord]) -> LifecycleEvent | None:
    if not commits:
        return None
    ordered = sorted(commits, key=lambda c: c.timestamp)
    first = ordered[0].timestamp
    if first.tzinfo is None:
        first = first.replace(tzinfo=timezone.utc)
    return LifecycleEvent(
        kind="pioneer_window",
        when=first,
        label="history_start",
        stage_hint="pioneer",
        confidence=0.8,
        source="git-history",
        meta={"early_commits": min(20, len(ordered))},
    )


def fetch_security_events(
    owner: str,
    repo: str,
    *,
    token: str | None = None,
    max_items: int = 20,
) -> list[LifecycleEvent]:
    """Best-effort GitHub security advisories (fails soft offline)."""
    if os.environ.get("CODEEVOLVE_SKIP_GHSA", "").lower() in {"1", "true", "yes"}:
        return []
    tok = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    # Use dependabot / advisories endpoint when available
    url = (
        f"https://api.github.com/repos/{urllib.parse.quote(owner)}/"
        f"{urllib.parse.quote(repo)}/security-advisories?per_page={max_items}"
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "codeevolve",
    }
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    events: list[LifecycleEvent] = []
    for row in data[:max_items]:
        if not isinstance(row, dict):
            continue
        published = row.get("published_at") or row.get("updated_at")
        when = _parse_ts(str(published or ""))
        if not when:
            continue
        ghsa = str(row.get("ghsa_id") or row.get("cve_id") or "advisory")
        sev = str(row.get("severity") or "")
        events.append(
            LifecycleEvent(
                kind="security",
                when=when,
                label=ghsa,
                stage_hint="disturbance",
                confidence=0.92 if sev in {"critical", "high"} else 0.8,
                source="github-advisory",
                meta={"severity": sev, "summary": str(row.get("summary") or "")[:160]},
            )
        )
    return events


def collect_lifecycle_events(
    repo: Path | str,
    commits: list[CommitRecord],
    *,
    owner: str | None = None,
    name: str | None = None,
    include_ghsa: bool = True,
) -> EventCorpus:
    repo = Path(repo)
    corpus = EventCorpus()
    tags = list_tag_events(repo)
    corpus.tags_seen = len(tags)
    corpus.events.extend(tags)
    corpus.events.extend(revert_storm_events(commits))
    pe = pioneer_event(commits)
    if pe:
        corpus.events.append(pe)
    if include_ghsa and owner and name:
        sec = fetch_security_events(owner, name)
        if sec:
            corpus.events.extend(sec)
        else:
            corpus.notes.append("GHSA unavailable or empty (offline / no permission)")
    elif include_ghsa:
        corpus.notes.append("No owner/repo for GHSA fetch")
    corpus.events.sort(key=lambda e: e.when)
    return corpus
