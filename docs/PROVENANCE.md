# Provenance ledger & deliberation (0.16)

CodeEvolve does not model reasoning. It builds a **history of provenance** — including a black-box **state trajectory** — so humans and agents can deliberate over how a codebase evolved.

```
analyze → taxonomy / genetics / ecology / risk / hypotheses / dynamics
       → provenance ledger (records + evidence + frames)
       → query / pack / path-pack / timeline / resolve / expand-frame
```

## Concepts

| Concept | Role |
|---------|------|
| **ProvenanceRecord** | Atom of history (incl. `state_sample`, `impulse_response`, `selection_item`, …) |
| **EvidenceRef** | Typed pointer (`supports` / `contradicts` / `context` / `measures`) |
| **DeliberationFrame** | Claim + stance + evidence + falsifier + measure + questions |
| **Dynamics** | Joined monthly state vector, impulse responses, regime basins, path episodes |
| **path_pack** | Path-centric slice: lineage → episodes → graph links → frames |

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

## Deliberation loop

1. Pick a frame (`frame:stage`, `frame:basin`, `frame:selection`, `frame:delta:report`, `frame:response:*`, …)
2. Expand (`--frame`) / walk (`--resolve`)
3. Check falsifier / measure
4. Ask `suggested_questions` against fresh git / re-analyze with `--previous`

## Record kinds (0.15)

Core: `commit_delta` · `lineage` · `clade` · `code_type` · `lifecycle_event` · `changepoint` · `stage_segment` · `hypothesis` · `experiment` · `failure_point` · `drift` · `signal`

Dynamics / process: `state_sample` · `trajectory` · `impulse_response` · `regime_basin` · `path_episode` · `selection_item` · `report_delta`

Typed links: `coupling_edge` · `debt_item` · `gene_flow` · `clone_link` · `reticulation`

Micro: `blast_radius` · `symbol` · `cst_delta`

## Schema / MCP tools

```powershell
python -m codeevolve provenance --schema
python -m codeevolve provenance --schema-out schemas
python -m codeevolve evaluate --suite dynamics
# JSON-lines tool server:
# python -m codeevolve.mcp.server
```

Tool names: `provenance_pack` · `provenance_expand_frame` · `provenance_path_pack` · `provenance_resolve` · `provenance_timeline`

## Python

```python
from codeevolve import CodeEvolve
from codeevolve.provenance import build_dynamics, build_provenance_ledger

report = CodeEvolve(".").analyze(use_llm=False, ensure_slm=False)
print(report.dynamics["summary"])
ledger = report.provenance
print(ledger.deliberation_pack(path="src/")["frames"][:3])
print(ledger.path_pack("src/api.py")["episodes"])
print(ledger.expand_frame("frame:basin"))
```

See also [ECOLOGY.md](ECOLOGY.md) for event/changepoint calibration that feeds impulse responses.
