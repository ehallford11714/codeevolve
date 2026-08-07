# Deep hierarchy & ecological trend reports (0.11)

CodeEvolve classifies each path through a **nested keyword ontology**
(`architecture → api → rest`, `verification → unit`, …), uses those types to
**guide taxonomic breakouts**, then writes nested trees and prose about ecological trends.

## Commands

```powershell
# ASCII tree + typed branch narratives (markdown)
python -m codeevolve --repo . hierarchy
python -m codeevolve --repo . hierarchy --md-out built_trends.md

# Raw keyword classifications + ontology counts
python -m codeevolve --repo . keyword-taxonomy

# Full repo report includes the hierarchy section
python -m codeevolve --repo . report --md-out repo_report.md
```

## Ontology roots

| Root | Examples |
|------|----------|
| `architecture` | api, data, ui, domain, security, infra, ml |
| `verification` | unit, integration, e2e, fixture, benchmark |
| `knowledge` | guide, api_docs, architecture, changelog |
| `tooling` | build, lint, codegen, scripts |
| `utility` | parsing, serialize, time, io |

Leaves go 3–4 levels deep (e.g. `architecture/api/rest`, `architecture/ml/embeddings`).

## Outputs

| Field | Meaning |
|-------|---------|
| `taxonomy.keyword_taxonomy.hierarchy` | Nested JSON of what was built |
| `taxonomy.keyword_taxonomy.ascii_tree` | Printable tree |
| `taxonomy.clades[].code_type` / `type_path` | Dominant type per clade |
| `hierarchy_trends.markdown` | Written report: tree + ecology + Lehman + branch notes |
| `hierarchy_trends.branch_trends[]` | heating / cooling / stable per type key |

Breakout seeds prefer `type:{lineage}|dir:{top}` when classification confidence is high, so mixed directories split by what they contain rather than path alone.
