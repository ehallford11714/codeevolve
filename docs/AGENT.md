# CodeEvolve Agent

Native coding agent that **uses CodeEvolve as sensor + scorer** and a cognitive stack to improve a repository toward an objective.

```
objective
   → resume session report (frame:delta:report) when present
   → git worktree/branch session (on --apply)
   → analyze (CodeEvolve) + optional baseline tests (+ coverage when available)
   → seed steps from frame:basin / path frames (+ refactor plan)
   → cognition: graph_search sense → attention_rank → coalition (~12) → reflect → gated propose → compact
   → optional kernel subagents (typed impasse → kernel; path-tie uses precedent, not spawn)
   → propose via structured JSON tool-calling (apply_patch) or heuristic
   → blast-radius preview (widen fence or refuse)
   → HITL (--approve) → patch engine (AST/CST symbol fence, fail-closed hunks)
   → verify_cmd / tests + coverage gate + CI gate
   → re-analyze; accept only if objective improves; commit on work branch
   → write pr_pack.md (frames, falsifiers, scores) · persist session.json
   → budgets / cost logging stop the loop when exceeded
```

## Cognitive stack

| Layer | Role |
|-------|------|
| **Memory** | Working / episodic / semantic + **Park-style retrieve** (recency × relevance × importance; graph-linked boost) |
| **RAG** | Semantic code chunks via `taxonomy.rag` (default **in-memory** vector store) |
| **Morphemes** | Identifier/path morphology mapped onto the CodeEvolve keyword ontology |
| **Sense** | **`graph_search` before reflect** (precedent + previous-report delta; `traverse=rw` on continue, `pivot` on spawn) |
| **Coalition** | ~12-node broadcast (`attention_rank` + `steiner_join` / knowledge slice / `at_pivot("propose")`) into **reflect** and `propose_action` (heuristic + LLM) |
| **Reflection** | Stance: `continue` \| `pivot` \| `stop` \| `spawn` |
| **Action** | Plans remaining tools after sense; dual-process gate (heuristic unless empty coalition / typed impasse / overridden) |
| **Tools** | `file_read`, `file_list`, `grep`, `rag_query`, `morpheme_scan`, `memory_*`, `provenance_hint`, **`graph_search` (registered sense organ, every cognition cycle)**, `web_search`, optional `shell` |
| **Tool-calling** | Structured JSON schemas (`apply_patch`, `done`, …) preferred over free-form |
| **Frame seed** | Prefer `frame:basin` / `frame:delta` paths over cold refactor waves |
| **Session delta** | `session.json` + previous report → `frame:delta:report` memory across runs |
| **Patch engine** | Unified hunks, fail-closed apply, **AST** (Python) / tree-sitter symbol fence |
| **Blast preview** | Co-change neighbors widen fence or refuse huge blast before apply |
| **Git session** | Branch + optional worktree; commit accepted rounds |
| **Tests / CI** | Auto-detect runners; `pass_tests` / `pass_tests+cov`; coverage + CI gates |
| **PR pack** | `pr_pack.md` with frames, falsifiers, scores (`gh pr comment --body-file`) |
| **Budget / HITL** | Wall/cost/token/round caps; `--approve` before write |
| **Compaction** | Compresses traces; **does not drop `overridden` / reflexion notes** |
| **Kernel subagents** | Spawned under atomic kernel objectives with path locks |

`graph_search` is a **registered sense organ** on the default tool registry. Each cognition cycle calls it **before reflect** (`precedent=true`, previous-report `delta` when present; `traverse=rw` on continue, `pivot` on spawn). Hits (ids / family / pivot / flow.summary) go into working memory — not `tool:ok`. Empty graphs fail closed (`insufficient`).

The round is a **gated working-memory bus**: sense → attention_rank → coalition (~12 nodes) → reflect/propose → write-back. Reflection and LLM propose both see coalition `frame_ids`, decisions, falsifiers, `allowed_because`/`overridden`. Write-back closes `valid_to` on prior decisions for the same path/frame; precedent ignores expired windows. Repeated agent-trace `(path, frame_ids, outcome)` compiles a fence/blast preference (never from silent git history; needs 2+ traces). Rollback writes an episodic note plus a `reflection` node linked `overridden` / `falsified_by` on the live graph (next sense sees it without re-parse) and jsonl. Kernel subagents run the same sense-first bus (`graph_search` before reflect, no duplicate search). Typed impasses map `insufficient→investigate`, verify-fail→`stabilize`, accepted-without-gain→`contain`, blast/fence refuse→`stabilize_path`; a path tie uses `precedent_search` instead of spawning. Not a GWT/LIDA/Soar port; no Kumar P@5/MTT claims.

```powershell
python -m codeevolve agent --list-providers
python -m codeevolve --repo . agent --objective reduce_debt --max-subagents 2
python -m codeevolve --repo . agent --objective pass_tests+cov --apply --auto-approve
python -m codeevolve --repo . agent --apply --approve --max-cost-usd 1.0
python -m codeevolve --repo . agent --previous-report .codeevolve/report.json
python -m codeevolve graph --from-agent .codeevolve/agent --search investigate --flow
# after a run: gh pr comment --body-file .codeevolve/agent/pr_pack.md
python -m codeevolve evaluate --suite agent
python -m codeevolve evaluate --suite all --offline   # agent is included; scores objective delta / rollback
```

MCP: `evolve_toward_objective`, `spawn_kernel_subagents`, `agent_cognition_info`, `context_graph`.

## Kernel objectives

| Kernel | Intent |
|--------|--------|
| `stabilize` | Raise stability / cut revert risk |
| `contain` | Fence blast-radius / coupling |
| `pay_down` | Debt markers |
| `evolve` | Forward change after stabilize |
| `investigate` | Read/grep/RAG until evidence exists |
| `search` | Web + repo search |
| `test` | Close test gaps |
| `document` | Path-fence / debt notes |

```python
from codeevolve.agent import spawn_subagents, Objective

spawn_subagents(".", Objective.parse("reduce_debt"), ["investigate", "pay_down"], allow_web=False)
```

## Objectives

| Spec | Optimizes |
|------|-----------|
| `follow_refactor` | Next evidence-linked refactor step (default) |
| `reduce_debt` | Minimize `debt.score` |
| `raise_stability` | Maximize `stability.composite` |
| `reduce_risk` | Minimize failure-point count |
| `stabilize_path` | Focus fence on `--path` |
| `pass_tests` | Maximize detected test/CI score |
| `pass_tests+cov` | Same + require coverage report / non-decreasing coverage |
| `metric:debt.score:min` | Custom dotted metric |

## Model endpoints (SLM / GPU / cloud)

Default `--llm auto` picks local SLM/HF by VRAM, else OpenAI → Anthropic → Grok → Kimi/K3 → OpenRouter. See [CLOUD.md](CLOUD.md).

```powershell
python -m codeevolve --repo . agent --provider openai --model gpt-4o
python -m codeevolve --repo . agent --provider grok
python -m codeevolve --repo . agent --provider kimik3
python -m codeevolve --repo . agent --llm slm --model-tier large
```

## Artifacts

- `.codeevolve/agent/run.json` — full `AgentRun` (budget, git, tests, pr_pack, session)
- `.codeevolve/agent/session.json` — last report path / score for resume deltas
- `.codeevolve/agent/pr_pack.md` + `pr_pack.json` — deliberation-backed review body
- `.codeevolve/agent/budget.json` — cost / wall / token tracker
- `.codeevolve/agent/cognition.json` — latest cognitive state
- `.codeevolve/agent/memory.json` — persisted memory (includes delta notes)
- `.codeevolve/agent/round_*/proposal.json` + `blast.json` + `ci_gate.json`
- `.codeevolve/agent/subagents/*.json` — kernel subagent reports
- `.codeevolve/worktrees/*` — disposable apply worktrees (removed on session end)

## Rules

- Prefer frames/packs over inventing history
- `stance=insufficient` → investigate/search kernels, do not hallucinate motive
- Path fence before hotspot edits; patch engine fail-closed on hunk/symbol mismatch
- Measure with re-analyze + objective/tests/CI; rollback on verify/objective failure
- Use `--approve` for HITL; budgets stop the loop (`budget_stop`)
