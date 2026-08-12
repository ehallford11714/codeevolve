---
name: codeevolve
description: >-
  Analyzes git history with CodeEvolve to build evolutionary provenance —
  taxonomy/clades, ecology stages, dynamics trajectories, and deliberation
  frames (claim→evidence→falsifier). Also runs the native objective coding
  agent (evolve_toward_objective / `codeevolve agent`) to propose or apply
  bounded improvements scored by re-analysis. Use when the user wants to parse
  a codebase's evolution, improve toward an objective, understand why hotspots
  exist, compare reports over time, prepare a path fence pack before edits, or
  connect MCP tools named analyze_repo / provenance_* / viz_phylogeny /
  evolve_toward_objective. Prefer evidence packs over inventing rationale.
---

# CodeEvolve — evolutionary provenance for agents

CodeEvolve does **not** invent “why this line exists.” It builds a **history of provenance** so you can deliberate with evidence.

## When to use

- User asks how a repo evolved, what stage it is in, or what is risky to touch
- User wants a phylogeny / clade / parsimony picture of the codebase (`viz_phylogeny`)
- Before large refactors: need path-centric provenance (blast, episodes, frames)
- PR/CI: compare current analyze to a previous `report.json`
- MCP tools `analyze_repo` or `provenance_*` are available

## Connect (MCP)

Project config: `.cursor/mcp.json` launches:

```text
python -m codeevolve.mcp
```

Install CodeEvolve in the environment Cursor uses:

```powershell
pip install -e "path\to\codeevolve"
# or from GitHub:
pip install "git+https://github.com/ehallford11714/codeevolve.git"
```

Reload MCP / restart Cursor after install. Tools: `analyze_repo`, `provenance_*`, `viz_phylogeny`, `evolve_toward_objective`, `spawn_kernel_subagents`, `agent_cognition_info`.

## Standard workflow

1. **Analyze** the target codebase (local path or `owner/repo`):

   - MCP: `analyze_repo` with `repo`, optional `max_commits` (200), `out`, `path`
   - CLI: `python -m codeevolve --repo <path|owner/repo> analyze --out .codeevolve/report.json`

2. **Deliberate** with the returned `report_path`:

   - `provenance_pack` → frames + howto
   - Pick a frame id (`frame:basin`, `frame:stage`, `frame:risk:*`, `frame:selection`, …)
   - `provenance_expand_frame` with `frame` + `from_report`
   - Before editing a file: `provenance_path_pack` with that `path`

3. **Decide** only after checking `falsifier` and `measure`. If stance is `insufficient`, say so — do not hallucinate motive.

4. **Improve toward an objective** (native cognitive agent):

   - MCP: `evolve_toward_objective` with `repo` + `objective`, `apply=false` first
   - Stack: in-memory notes, RAG semantic chunks, morphemes, reflection, tooling (`grep`/`web_search`/…), compaction, kernel subagents
   - Spawn helpers: `spawn_kernel_subagents`, inspect via `agent_cognition_info`
   - CLI: `python -m codeevolve --repo . agent --objective reduce_debt`
   - Review `.codeevolve/agent/` (`cognition.json`, `subagents/`), then `--apply`
   - Agent re-scores via CodeEvolve and rolls back non-improving rounds

5. **Temporal**: if a previous report exists, re-analyze with `--previous` and open `frame:delta:report`.

## CLI fallbacks (no MCP)

```powershell
python -m codeevolve --repo . analyze --out .codeevolve/report.json
python -m codeevolve provenance --from-report .codeevolve/report.json --pack
python -m codeevolve provenance --from-report .codeevolve/report.json --path-pack src/api.py
python -m codeevolve provenance --from-report .codeevolve/report.json --frame frame:basin
python -m codeevolve viz --report .codeevolve/report.json --out .codeevolve/viz.html
python -m codeevolve viz --report .codeevolve/report.json --out .codeevolve/builder.html --kind 3d
python examples/demo_dynamics.py
```

## Rules

- Prefer packs/frames over dumping full `report.json` into context
- Cite `frame:*` ids and evidence `record_id`s in answers
- Absence of evidence → `insufficient`, not a story
- Do not claim chaos/Lyapunov or invent line-level archaeology
- Env defaults for agents: `CODEEVOLVE_SKIP_HF=1`, `CODEEVOLVE_TAXONOMY_HEURISTIC=1`

## Docs in repo

- `docs/AGENT.md` — objective coding agent
- `docs/PROVENANCE.md` — ledger & frames
- `docs/DYNAMICS.md` — state trajectory
- `docs/DEMO_DYNAMICS.md` — real-tag demo
- `docs/MCP.md` — MCP setup
- `docs/VIZ.md` — phylogeny / clade / parsimony gallery
- `docs/TUTORIAL.md` — end-to-end
