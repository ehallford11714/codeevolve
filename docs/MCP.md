# CodeEvolve MCP

Connect Cursor (or any MCP host) so agents can **analyze a codebase** and **deliberate with provenance packs** instead of inventing history.

**Agents start here:** [AGENTS.md](../AGENTS.md) (install → MCP → tool loop → rules).

## Install

```powershell
git clone https://github.com/ehallford11714/codeevolve.git
cd codeevolve
pip install -e .
```

The host must run the same Python env where `codeevolve` is installed.

## Cursor

This repo ships [`.cursor/mcp.json`](../.cursor/mcp.json):

```json
{
  "mcpServers": {
    "codeevolve": {
      "command": "python",
      "args": ["-m", "codeevolve.mcp"],
      "env": {
        "CODEEVOLVE_SKIP_HF": "1",
        "CODEEVOLVE_SKIP_EMBED": "1",
        "CODEEVOLVE_TAXONOMY_HEURISTIC": "1",
        "CODEEVOLVE_SKIP_GHSA": "1",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

1. Open the repo in Cursor (or merge the `mcpServers.codeevolve` block into your user MCP config).
2. Ensure `python -m codeevolve.mcp --help` works in that environment.
3. Reload MCP / restart Cursor.
4. Confirm tools: `analyze_repo`, `provenance_pack`, `provenance_expand_frame`, `provenance_path_pack`, `provenance_resolve`, `provenance_timeline`, `viz_phylogeny`, `evolve_toward_objective`.

Agent skill (project): [`.cursor/skills/codeevolve/SKILL.md`](../.cursor/skills/codeevolve/SKILL.md). Objective agent: [AGENT.md](AGENT.md).

## Tool loop

| Step | Tool | Purpose |
|------|------|---------|
| 1 | `analyze_repo` | Parse local path / `owner/repo` / GitHub URL → `report.json` + pack |
| 2 | `provenance_pack` | Frames (claim → evidence → falsifier) |
| 3 | `provenance_expand_frame` | Drill into `frame:basin`, `frame:risk:*`, … |
| 4 | `provenance_path_pack` | Before editing a hotspot path |
| 5 | `provenance_resolve` / `provenance_timeline` | Walk evidence / chronology |
| 6 | `evolve_toward_objective` | Dry-run or apply bounded improvements scored by re-analysis |
| 7 | `viz_phylogeny` | Phylogeny / clades / Fitch parsimony / gene-flow from `report.json` |

`analyze_repo` arguments:

- `repo` (required) — path, `owner/name`, or URL
- `max_commits` — default `200`
- `out` — report path (default `.codeevolve/report.json`)
- `pack_out` — optional deliberation pack JSON
- `path` — optional path focus in the returned pack

Later tools take `from_report` (path returned by step 1). If omitted, the server looks for `./.codeevolve/report.json`.

## Manual / other hosts

```powershell
python -m codeevolve.mcp
# legacy JSON lines (tests / simple scripts):
python -m codeevolve.mcp --jsonl
```

Stdio uses MCP JSON-RPC with `Content-Length` framing (no extra MCP SDK dependency).

## CLI without MCP

```powershell
python -m codeevolve --repo . analyze --out .codeevolve/report.json
python -m codeevolve provenance --from-report .codeevolve/report.json --pack
python -m codeevolve viz --report .codeevolve/report.json --out .codeevolve/viz.html
python -m codeevolve viz --report .codeevolve/report.json --out .codeevolve/builder.html --kind 3d
python -m codeevolve provenance --schema-out schemas
```

## Discipline

- Prefer frames/packs over dumping full reports into context
- Respect `falsifier` / `measure`; stance `insufficient` when the record is silent
- Do not invent line-level “why” or chaos branding

See [PROVENANCE.md](PROVENANCE.md), [DYNAMICS.md](DYNAMICS.md), [TUTORIAL.md](TUTORIAL.md).
