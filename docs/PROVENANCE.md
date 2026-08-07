# Provenance ledger & deliberation (0.16)

CodeEvolve does **not** model reasoning. It builds a **history of provenance** so humans and agents can *deliberate over* how a codebase evolved — claim by claim, with evidence and falsifiers.

```
analyze → taxonomy / genetics / ecology / risk / hypotheses / dynamics
       → provenance ledger (records + evidence links + deliberation frames)
       → query / pack / path-pack / timeline / resolve / expand-frame
```

## Why provenance (product rationale)

| Pressure | Without a ledger | With a ledger |
|----------|------------------|---------------|
| Agents / tools | Dump entire `report.json` into context | Compact packs with howto + frames |
| PR / CI | Score strips without argument structure | Frames with falsifiers on the comment/dashboard |
| Ecology + risk | Parallel JSON blobs | One graph: event → impulse → basin → risk |
| Epistemics | Easy to hallucinate “why” | `insufficient` is first-class when the record is silent |

Adjacent tools either reconstruct narrative “why” with LLMs, or attest build provenance (SLSA). CodeEvolve’s niche is **evolutionary provenance for deliberation** — see also [DYNAMICS.md](DYNAMICS.md).

## Concepts

| Concept | Role | Rationale |
|---------|------|-----------|
| **ProvenanceRecord** | Atom of history | One typed fact agents can cite |
| **EvidenceRef** | `supports` / `contradicts` / `context` / `measures` | Explicit role beats free-text “related” |
| **DeliberationFrame** | Claim + stance + evidence + falsifier + measure + questions | Unit of accept/reject before acting |
| **Dynamics** | State trajectory, impulses, basins, episodes | Joins time series into deliberable structure |
| **path_pack** | Path-centric slice | Hotspot edits need local provenance, not the whole repo |

## Commands

```powershell
python -m codeevolve --repo . provenance --pack
python -m codeevolve --repo . provenance --path-pack src/api.py
python -m codeevolve --repo . provenance --timeline
python -m codeevolve --repo . provenance --frame frame:basin
python -m codeevolve --repo . provenance --frame frame:delta:report
python -m codeevolve --repo . provenance --resolve frame:stage --depth 2
python -m codeevolve provenance --from-report report.json --pack --out deliberation.json
```

### Why each operation

| Flag | Purpose | Rationale |
|------|---------|-----------|
| `--pack` | Frames + records + timeline + howto | Default agent/tool payload |
| `--path-pack` | Lineage, episodes, blast, symbols, CST, frames | Pre-edit Chesterton pack for one path |
| `--timeline` | Chronological slice | Backbone for “what happened when” |
| `--frame` | Expand one claim with evidence + chain | Deep dive without loading the whole ledger |
| `--resolve` | Walk EvidenceRef edges | Follow claim → anchors → lineages |
| `--from-report` | Offline rebuild | CI and agents reuse saved JSON |

## Deliberation loop

1. **Pick a frame** (`frame:stage`, `frame:basin`, `frame:selection`, `frame:delta:report`, `frame:response:*`, `frame:risk:*`, `frame:exp:*`, …)
2. **Expand** (`--frame`) or **walk** (`--resolve`)
3. **Check falsifier / measure** before acting
4. **Ask `suggested_questions`** against fresh git or re-analyze (`--previous` for temporal frames)

Absence of evidence → stance `insufficient`. Do not invent motive.

## Record kinds

### Core evolutionary structure

`commit_delta` · `lineage` · `clade` · `code_type` · `lifecycle_event` · `changepoint` · `stage_segment` · `hypothesis` · `experiment` · `failure_point` · `drift` · `signal`

**Rationale:** these already exist on `analyze`; the ledger makes them queryable and linkable.

### Dynamics / process (0.15)

`state_sample` · `trajectory` · `impulse_response` · `regime_basin` · `path_episode` · `selection_item` · `report_delta`

**Rationale:**

- **State / trajectory** — FEAST/Lehman feedback view: observe \(x(t)\) before simulating.
- **Impulse response** — events should show Δx, not sit beside series unused.
- **Basin** — stages as occupancy of a regime, not only a label.
- **Path episode** — files have multiple “lives”; pack them for edit decisions.
- **Selection items** — Issues/PRs are *stated* evidence (tagged `stated`).
- **Report delta** — deliberation over *time* between analyzes.

### Typed links (kind hygiene)

`coupling_edge` · `debt_item` · `gene_flow` · `clone_link` · `reticulation`

**Rationale:** earlier drafts overloaded `commit_delta` / `failure_point`, which broke filter trust for agents.

### Micro-provenance (0.16)

`blast_radius` · `symbol` · `cst_delta`

**Rationale:** risk frames need structural measures (who co-changes, which symbols, CST node shifts) before “contain” refactors — without diving to line-level LLM archaeology.

## Frames worth knowing

| Frame | Claim about | Typical falsifier |
|-------|-------------|-------------------|
| `frame:stage` | Ecological stage | Opposing event/CP within ~45d |
| `frame:basin` | Trajectory occupies a basin | Occupancy drops sharply |
| `frame:selection` | Issue/PR pressure | Bug backlog + merge health improve |
| `frame:delta:report` | What flipped since previous | Re-analyze shows no material deltas |
| `frame:response:*` | Post-shock Δx | State returns to pre-event mean |
| `frame:risk:*` | Hotspot / weakness | Cleared without regressing coupling/reverts |
| `frame:exp:*` / `frame:branch:*` | Next experiment / typed heat | Churn direction reverses |

## Schema / MCP tools

**Why:** packs are an API. Schema catches drift; MCP-shaped tools let agents call deliberation ops without scraping CLI help.

```powershell
python -m codeevolve provenance --schema
python -m codeevolve provenance --schema-out schemas
python -m codeevolve evaluate --suite dynamics
# MCP stdio (Cursor / hosts) — see docs/MCP.md
python -m codeevolve.mcp
```

| Tool | Does |
|------|------|
| `analyze_repo` | Live analyze path / GitHub → report + pack |
| `provenance_pack` | Deliberation pack |
| `provenance_expand_frame` | Frame + evidence + chain |
| `provenance_path_pack` | Path-centric pack |
| `provenance_resolve` | Evidence walk |
| `provenance_timeline` | Chronological slice |

Files: `schemas/deliberation_pack.schema.json`, `schemas/mcp_tools.json`. Cursor: `.cursor/mcp.json` + `.cursor/skills/codeevolve/SKILL.md`.

## Python

```python
from codeevolve import CodeEvolve
from codeevolve.provenance import build_dynamics, build_provenance_ledger, validate_deliberation_pack

report = CodeEvolve(".").analyze(use_llm=False, ensure_slm=False)
print(report.dynamics["summary"])
ledger = report.provenance
pack = ledger.deliberation_pack(path="src/")
assert validate_deliberation_pack(pack) == []
print(ledger.path_pack("src/api.py")["blast_radius"])
print(ledger.expand_frame("frame:basin"))
```

## What we deliberately do not do

| Avoid | Why |
|-------|-----|
| Hallucinated line-level “why” | Competes with archaeology tools; only allow polish behind evidence IDs |
| Chaos / Lyapunov branding | Histories usually too short; prefer velocity, impulse, occupancy |
| Owning SLSA signing | Meet build provenance at release events if attestations exist |
| Full PROV-O export (yet) | Stabilize the internal graph first |

See [ECOLOGY.md](ECOLOGY.md) for event/changepoint inputs and [DYNAMICS.md](DYNAMICS.md) for the trajectory layer.
