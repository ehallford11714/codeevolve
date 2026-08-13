# Agents — connect to CodeEvolve

Use this repo to **parse a codebase’s git history** into evolutionary provenance: taxonomy/clades, ecology stage, dynamics trajectory, and deliberation frames (`claim → evidence → falsifier`). Do **not** invent why a line exists when the record is silent — return stance `insufficient`.

Full MCP detail: [docs/MCP.md](docs/MCP.md) · Human overview: [README.md](README.md)

## 1. Install

```powershell
pip install codeevolve
# verify
python -m codeevolve.mcp --help
```

From source:

```powershell
git clone https://github.com/ehallford11714/codeevolve.git
cd codeevolve
pip install -e .
# verify
python -m codeevolve.mcp --help
```

The MCP host must use the **same Python** where `codeevolve` is installed.

## 2. Connect MCP (Cursor)

This repository includes:

| File | Role |
|------|------|
| [`.cursor/mcp.json`](.cursor/mcp.json) | Stdio server: `python -m codeevolve.mcp` |
| [`.cursor/skills/codeevolve/SKILL.md`](.cursor/skills/codeevolve/SKILL.md) | When/how to call tools |

Open this repo in Cursor (or copy the `mcpServers.codeevolve` block into your user MCP config), reload MCP, confirm tools below appear.

Other hosts: run `python -m codeevolve.mcp` (or `codeevolve-mcp`) as a stdio MCP server. Protocol is JSON-RPC with `Content-Length` framing (no extra MCP SDK).

Recommended env (already in `.cursor/mcp.json`):

```text
CODEEVOLVE_SKIP_HF=1
CODEEVOLVE_SKIP_EMBED=1
CODEEVOLVE_TAXONOMY_HEURISTIC=1
CODEEVOLVE_SKIP_GHSA=1
PYTHONUTF8=1
```

## 3. Tool loop (parse any codebase)

| Step | Tool | Args |
|------|------|------|
| Analyze | `analyze_repo` | `repo` = local path, `owner/name`, or GitHub URL; optional `max_commits`, `out`, `path`, `pack_out` |
| Pack | `provenance_pack` | `from_report` = path from step 1 |
| Frame | `provenance_expand_frame` | `from_report`, `frame` (e.g. `frame:basin`) |
| Path fence | `provenance_path_pack` | `from_report`, `path` before editing a hotspot |
| Walk | `provenance_resolve` / `provenance_timeline` | evidence chain / chronology |
| Improve | `evolve_toward_objective` | `repo`, `objective`, optional `path`, `max_rounds`, `apply`, cognition/spawn flags |
| Kernels | `spawn_kernel_subagents` | Spawn stabilize/contain/pay_down/investigate/search/… subagents |
| Cognition | `agent_cognition_info` | Memory/RAG/morpheme/tools/kernel catalog |
| Viz | `viz_phylogeny` | Phylogeny with semantic `type_path` divisions / clades / Fitch / gene-flow HTML+SVG |

Default report path if `out` omitted: `.codeevolve/report.json`.

### Objective improve loop (native agent)

When the goal is to **change code toward a measurable objective**, use the built-in agent (not inventing history):

1. Dry-run: `evolve_toward_objective` with `apply=false` (default)
2. Review `rounds[].proposal` (`frame_ids`, `falsifier`, `edit_previews`)
3. Apply: same tool with `apply=true` (+ `verify_cmd` if tests exist)
4. Agent re-analyzes with previous report and **rolls back** rounds that worsen signals

Objectives: `follow_refactor` · `reduce_debt` · `raise_stability` · `reduce_risk` · `stabilize_path` · `metric:debt.score:min`

**Models (default `auto`):** local SLM / GPU-sized HF Qwen, or cloud `openai` · `anthropic` · `grok` · `kimik3`/`kimi` · `openrouter` · `custom` (`--base-url`). Configure via `--provider`/`--model`/`--api-key`, env keys, or `.codeevolve/models.json` (see [docs/CLOUD.md](docs/CLOUD.md), [docs/AGENT.md](docs/AGENT.md)).

```powershell
python -m codeevolve agent --list-providers
python -m codeevolve --repo . agent --provider grok --model grok-3-mini
```

## 4. CLI fallback (no MCP)

```powershell
python -m codeevolve --repo <path|owner/repo> analyze --out .codeevolve/report.json
python -m codeevolve provenance --from-report .codeevolve/report.json --pack
python -m codeevolve provenance --from-report .codeevolve/report.json --path-pack src/api.py
python -m codeevolve provenance --from-report .codeevolve/report.json --frame frame:basin
python -m codeevolve viz --report .codeevolve/report.json --out .codeevolve/viz.html
python -m codeevolve viz --report .codeevolve/report.json --out .codeevolve/builder.html --kind 3d
python -m codeevolve --repo <path|owner/repo> agent --objective reduce_debt --max-rounds 2
python -m codeevolve.agent --repo . --objective follow_refactor --apply --verify-cmd "pytest -q"
```

## 5. Rules

- Prefer frames/packs over dumping full `report.json` into context
- Cite `frame:*` ids and evidence record ids in answers
- Respect `falsifier` and `measure`; do not claim chaos/Lyapunov or line-level archaeology
- Re-analyze with a previous report when temporal deltas matter (`frame:delta:report`)
- For code changes: prefer `evolve_toward_objective` dry-run before `apply=true`

## 6. Schemas

- `schemas/mcp_tools.json` — tool descriptors
- `schemas/deliberation_pack.schema.json` — pack shape  
Regenerate: `python -m codeevolve provenance --schema-out schemas`
