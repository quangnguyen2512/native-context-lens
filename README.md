# Native Context Lens

**Governed Event-Sourced Context Engine, Markdown-vs-Native Benchmark Suite & Malleable Artifact Workbench** built directly around the architectural invariants of [`withnative/native`](https://github.com/withnative/native).

## Why This Exists
Plain Markdown wikilink vaults fail multi-agent teams in three predictable ways:
1. **Token burn & turn explosion:** Finding which active decision blocks a deal (`northwind-deal -> pricing-review -> decision-2026-09-12 -> superseded by decision-2026-10-02 -> waiting on finance-sign-off`) forces an agent through 6 tool turns, full-file reads, and vault-wide backlink greps.
2. **Silent stale-context traps:** Old decision documents rarely get back-patched when superseded weeks later — causing naive Markdown agents to cite revoked rules with 100% confidence.
3. **Zero caller governance:** Raw filesystem access cannot enforce fail-closed caller ACLs or sandboxed artifact capability boundaries (`native.mdx.artifact.v2` / `native.html.artifact.v2`).

**Native Context Lens** implements a runnable Python 3.12 + SQLite WAL + FastAPI reference workbench proving all four invariants end-to-end.

---

## Core Architecture
```text
MCP/API operation contract
  -> caller identity + fail-closed authorization (`authorized_records` CTE)
  -> governed domain operations
  -> BEGIN IMMEDIATE (SQLite WAL): append SHA-256 hash-chained event + project atomically
  -> authoritative `events` log (single source of truth)
  -> deterministic projectors -> `records` + `links` + `facets` + `permissions` + `freshness_alerts`
```

- **Deterministic Replay (`rebuild_projections()`):** Drops all 5 derived projection tables inside `BEGIN IMMEDIATE` and replays all `57` authoritative events in `~4.2 ms`, matching the pre-drop SHA-256 projection digest bit-for-bit (`d446657637e5...`).
- **Fail-Closed Caller ACLs:** Explicit `deny` overrides `allow`; record-level `allow` overrides collection inheritance; unauthorized records vanish from SQL queries, links, freshness alerts, recursive blocker traces, AND rendered artifacts with zero ID/title leakage.
- **Automatic Stale-Context Cascade:** Superseding or updating an upstream decision runs a recursive SQL CTE inside the same write transaction, flagging every downstream dependent with `STALE_DEPENDENCY` freshness alerts.
- **Malleable Artifact Runtime (`v2`):** Validates `native.mdx.artifact.v2` and `native.html.artifact.v2` contracts (`native.collection-envelope.v1`, explicit `capability_requests`), renders two live views (**Compact Decision Table** vs **Kanban Dependency Cards**) over the exact same governed collection, exports valid Native `Document kind:artifact` payloads, and rejects forbidden capabilities (e.g. `shell.exec`) or unauthorized callers fail-closed with `fallback_surface: null`.

---

## Verified Benchmark Results (25-Document Company Vault)
Executed deterministically over `sample_vault/*.md` (`25` Markdown files, `12,396` total tokens) across 5 multi-hop organizational blocker chains:

| Scenario | MD Turns | MD Payload Tok | MD Cumul. Tok | Native 1-SQL Tok | Payload Savings | Cumul. Savings | Native Latency | Terminal Blocker |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| **Northwind Enterprise Deal** | 6 | 5,940 | 24,394 | 235 | **25.28x** | **103.80x** | 1.79 ms | `finance-sign-off` |
| **Enterprise Security Audit** | 6 | 3,633 | 12,472 | 256 | **14.19x** | **48.72x** | 1.15 ms | `kms-key-ceremony` |
| **SOC 2 Vendor Approval** | 6 | 4,206 | 16,594 | 255 | **16.49x** | **65.07x** | 0.66 ms | `legal-redline-signoff` |
| **Q4 GA Launch Freeze** | 6 | 3,205 | 10,884 | 251 | **12.77x** | **43.36x** | 0.55 ms | `load-test-certification` |
| **API v1 Deprecation** | 6 | 3,983 | 15,951 | 247 | **16.13x** | **64.58x** | 0.58 ms | `sdk-v3-release-gate` |
| **Aggregate (All 5 Chains)** | **6.0** | **20,967** | **80,295** | **1,244** | **16.85x** | **64.55x** | **< 2 ms** | **5/5 (100%)** |

- **Turns per query:** `6.0` (Markdown agent) -> **`1.0`** (`1` governed recursive SQL CTE).
- **Stale-decision accuracy:** Naive Markdown `0.0%` (trapped on all 5 superseded decisions) vs. Native **`100.0%`** (**100% error reduction**).

---

## Quickstart
```powershell
# 1. Run full pytest verification suite (12 tests)
$env:PYTHONPATH = "src"
python -m pytest -v

# 2. Run the head-to-head Markdown vs. Native SQLite benchmark CLI
python -m native_lens.cli benchmark
python -m native_lens.cli benchmark --format json

# 3. Verify drop-and-replay determinism from the authoritative events table
python -m native_lens.cli replay-check

# 4. Export a valid Native `Document kind:artifact` payload (ACL-filtered per caller)
python -m native_lens.cli export-artifact --view compact_decision_table --caller contractor
python -m native_lens.cli export-artifact --view kanban_dependency_cards --caller founder

# 5. Launch the Interactive Workbench UI at http://127.0.0.1:8790
python -m native_lens.cli serve --port 8790
```

## Key Files
- [`src/native_lens/engine.py`](src/native_lens/engine.py) — Event-sourced SQLite WAL engine, hash-chained `events`, atomic projections, fail-closed ACL CTE, stale-context cascade, 1-SQL blocker tracer, `rebuild_projections()`
- [`src/native_lens/benchmark.py`](src/native_lens/benchmark.py) — Real 25-file Markdown agent simulator vs. 1-SQL Native engine benchmark & report generators
- [`src/native_lens/artifacts.py`](src/native_lens/artifacts.py) — `native.mdx.artifact.v2` / `native.html.artifact.v2` manifest validator, dual-view renderer & `Document kind:artifact` exporter
- [`src/native_lens/app.py`](src/native_lens/app.py) & [`src/native_lens/static/index.html`](src/native_lens/static/index.html) — FastAPI REST API + zero-dependency interactive workbench UI
- [`tests/test_native_lens.py`](tests/test_native_lens.py) — 12 end-to-end unit, security, replay, benchmark & FastAPI tests
