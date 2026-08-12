"""Bounded shell tool (opt-in)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from codeevolve.agent.tools.registry import ToolResult

_BLOCK = (
    "rm -rf",
    "del /f",
    "format ",
    "mkfs",
    ":(){",
    "shutdown",
    "reboot",
)


def shell_run(root: Path, command: str, *, timeout: int = 60) -> ToolResult:
    cmd = (command or "").strip()
    if not cmd:
        return ToolResult(ok=False, name="shell", output="", error="empty command")
    low = cmd.lower()
    if any(b in low for b in _BLOCK):
        return ToolResult(ok=False, name="shell", output="", error="blocked dangerous command")
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        return ToolResult(
            ok=proc.returncode == 0,
            name="shell",
            output=out[:12000],
            error=None if proc.returncode == 0 else f"exit {proc.returncode}",
            meta={"returncode": proc.returncode},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ToolResult(ok=False, name="shell", output="", error=str(exc))
