# ARCHITECTURE — native-context-lens

Governed Context Engine, Markdown-vs-Native Benchmark Suite, and Malleable Artifact Workbench built to mirror and stress-test the core architecture invariants of `withnative/native`.

## Core Invariants
1. **Single Authoritative Event Log (`events`) + Atomic Projections:** Every mutation runs inside `BEGIN IMMEDIATE` SQLite WAL transaction, appending a SHA-256 hash-chained event and projecting deterministically into `records`, `links`, `facets`, `permissions`, and `freshness_alerts`. Projection tables are never an independent source of truth and can be dropped and replayed bit-for-bit via `rebuild_projections()`.
2. **Fail-Closed Caller Authorization:** Every query, recursive blocker trace, freshness alert lookup, and artifact envelope enforces caller identity (`caller_id` + `roles`) inside a parameterized SQL `authorized_records` CTE. Explicit `deny` overrides `allow`; records with record-level `allow` rules do not inherit broader collection access; unknown/unauthorized callers receive zero rows or `AuthorizationError` with no secret leakage.
3. **Automatic Stale-Context Cascade:** Superseding or mutating an upstream record triggers a deterministic recursive SQL CTE inside the same transaction that traverses all downstream dependents (`depends_on`, `references`, `waiting_on`, inverse `blocks`) and emits `STALE_DEPENDENCY` freshness alerts automatically.
4. **Malleable Artifact Runtime Fail-Closed Contract:** Artifacts declare `schema` (`native.mdx.artifact.v2` or `native.html.artifact.v2`), `inputs` (`native.collection-envelope.v1`), and explicit `capability_requests`. Host validation rejects unknown/dangerous capabilities or missing `input.read` with zero fallback surface.

## Directory Boundaries
```text
hn_freelance_bd8a5174d4a0_native_workstation/
├── ARCHITECTURE.md                  # System architecture & invariants
├── pyproject.toml                   # Python 3.12 package configuration
├── README.md                        # Quickstart, benchmark results & design notes
├── LOOM_SCRIPTS_AND_APPLICATION.md  # 3x 60s Loom scripts + 04 Surprising + form checklist
├── sample_vault/                    # 25 realistic company Markdown docs (5 multi-hop scenarios)
├── src/native_lens/
│   ├── models.py                    # Pydantic v2 domain, benchmark & artifact schemas
│   ├── engine.py                    # Event-sourced SQLite WAL engine, ACL CTE, stale cascade, replay
│   ├── vault.py                     # Markdown frontmatter + [[wikilink]] parser & event ingester
│   ├── benchmark.py                 # Markdown Agent Simulator vs 1-SQL Native Engine benchmark
│   ├── artifacts.py                 # native.mdx/html.artifact.v2 validator, dual renderer & exporter
│   ├── app.py                       # FastAPI REST API + static workbench server
│   ├── cli.py                       # CLI: benchmark, replay-check, export-artifact, serve
│   └── static/index.html            # Zero-dependency dark editorial interactive workbench
└── tests/test_native_lens.py        # End-to-end pytest verification suite
```

## Execution DAG
```text
sample_vault/*.md -> vault.py -> engine.py (BEGIN IMMEDIATE: events -> projections)
                                      │
          ┌───────────────────────────┼───────────────────────────┐
          ▼                           ▼                           ▼
   benchmark.py                 artifacts.py                    app.py
 (MD vs 1-SQL CTE)     (v2 manifest validator + 2 views)   (FastAPI + Workbench UI)
```
