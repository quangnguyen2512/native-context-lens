"""Comprehensive pytest verification suite for native-context-lens."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from native_lens.app import create_app
from native_lens.artifacts import (
    ArtifactAccessDeniedError,
    ArtifactRuntime,
    ArtifactValidationError,
)
from native_lens.benchmark import (
    BenchmarkRunner,
    format_benchmark_json,
    format_benchmark_markdown,
)
from native_lens.engine import (
    AuthorizationError,
    NativeContextEngine,
    RecordNotFoundError,
)
from native_lens.vault import load_vault_into_engine


@pytest.fixture()
def seeded_engine(tmp_path: Path) -> NativeContextEngine:
    db_file = tmp_path / "native_lens.sqlite3"
    engine = NativeContextEngine(db_file)
    load_vault_into_engine(engine)
    yield engine
    engine.close()


# ------------------------------------------------------------------
# 1. Event-Sourced SQLite Engine + Deterministic Replay Tests
# ------------------------------------------------------------------


def test_atomic_event_append_wal_and_deterministic_replay(seeded_engine: NativeContextEngine) -> None:
    journal_mode = seeded_engine.conn.execute("PRAGMA journal_mode;").fetchone()[0]
    assert str(journal_mode).lower() == "wal"
    assert seeded_engine.verify_event_hash_chain() is True

    # Perform additional live governed mutations
    seeded_engine.create_record(
        record_id="decision-2026-10-08",
        collection="launch_blockers",
        kind="decision",
        title="Decision 2026-10-08: Approved 19% Multi-Year Cap",
        status="active",
        owner="George (Founder)",
        summary="Finalized 19% ceiling after CFO margin check.",
        caller="founder",
    )
    seeded_engine.supersede_record(
        old_record_id="decision-2026-10-02",
        new_record_id="decision-2026-10-08",
        reason="Updated after CFO board review",
        caller="founder",
    )

    before_digest = seeded_engine.compute_projection_digest()
    replay = seeded_engine.rebuild_projections()

    assert replay.events_replayed > 50
    assert replay.chain_integrity_valid is True
    assert replay.deterministic_match is True
    assert replay.before_digest == before_digest
    assert replay.after_digest == before_digest

    # Verify superseded record state survived full projection drop + replay
    old_rec = seeded_engine.get_record("decision-2026-10-02", caller="founder")
    assert old_rec.status == "superseded"
    assert old_rec.superseded_by == "decision-2026-10-08"


def test_event_hash_chain_detects_tampering(seeded_engine: NativeContextEngine) -> None:
    assert seeded_engine.verify_event_hash_chain() is True
    # Tamper with an historical event payload in place
    seeded_engine.conn.execute(
        "UPDATE events SET payload_json = '{\"tampered\":true}' WHERE seq = 1"
    )
    assert seeded_engine.verify_event_hash_chain() is False


# ------------------------------------------------------------------
# 2. Fail-Closed Caller Authorization & ACL Isolation Tests
# ------------------------------------------------------------------


def test_fail_closed_acl_isolation_across_personas(seeded_engine: NativeContextEngine) -> None:
    founder_ids = {r.record_id for r in seeded_engine.query_records(caller="founder")}
    engineer_ids = {r.record_id for r in seeded_engine.query_records(caller="engineer")}
    contractor_ids = {r.record_id for r in seeded_engine.query_records(caller="contractor")}
    anon_ids = {r.record_id for r in seeded_engine.query_records(caller="anonymous")}

    assert len(founder_ids) == 25
    assert {"finance-sign-off", "kms-key-ceremony", "legal-redline-signoff"} <= founder_ids

    # Engineer (member): founder-only records fail closed
    assert len(engineer_ids) == 23
    assert "finance-sign-off" not in engineer_ids
    assert "kms-key-ceremony" not in engineer_ids
    assert "legal-redline-signoff" in engineer_ids

    # Contractor: founder-only AND internal-only records fail closed
    assert len(contractor_ids) == 22
    assert "finance-sign-off" not in contractor_ids
    assert "kms-key-ceremony" not in contractor_ids
    assert "legal-redline-signoff" not in contractor_ids

    # Anonymous: zero rows
    assert len(anon_ids) == 0

    # Direct read fails closed
    with pytest.raises(RecordNotFoundError):
        seeded_engine.get_record("finance-sign-off", caller="contractor")
    with pytest.raises(RecordNotFoundError):
        seeded_engine.get_record("northwind-deal", caller="anonymous")

    # Blocker trace for contractor MUST NEVER leak founder-only terminal record
    contractor_trace = seeded_engine.trace_blocker_chain("northwind-deal", caller="contractor")
    traced_ids = {h.record_id for h in contractor_trace.chain}
    assert "northwind-deal" in traced_ids
    assert "decision-2026-10-02" in traced_ids
    assert "finance-sign-off" not in traced_ids
    assert "finance-sign-off" not in contractor_trace.compact_payload_json

    # Links list for contractor MUST NEVER leak edges pointing to restricted records
    contractor_links = seeded_engine.list_links(caller="contractor")
    for lnk in contractor_links:
        assert lnk.source_id not in {"finance-sign-off", "kms-key-ceremony", "legal-redline-signoff"}
        assert lnk.target_id not in {"finance-sign-off", "kms-key-ceremony", "legal-redline-signoff"}

    # Explicit DENY overrides collection allow
    seeded_engine.grant_acl("record", "northwind-deal", "role:member", "deny", caller="founder")
    with pytest.raises(RecordNotFoundError):
        seeded_engine.get_record("northwind-deal", caller="engineer")

    # Unauthorized writes fail closed
    with pytest.raises(AuthorizationError):
        seeded_engine.create_record(
            record_id="rogue-doc",
            collection="launch_blockers",
            kind="decision",
            title="Unauthorized write",
            status="active",
            owner="External",
            summary="Should fail",
            caller="contractor",
        )
    with pytest.raises(AuthorizationError):
        seeded_engine.grant_acl("collection", "launch_blockers", "role:contractor", "allow", caller="engineer")


# ------------------------------------------------------------------
# 3. Stale-Context Propagation Tests
# ------------------------------------------------------------------


def test_stale_context_cascade_on_supersedes_and_update(seeded_engine: NativeContextEngine) -> None:
    # Vault ingestion already projected supersedes links -> downstream dependents must be flagged STALE
    alerts = seeded_engine.list_freshness_alerts(caller="founder", status="open")
    by_affected = {(a.trigger_record_id, a.affected_record_id): a for a in alerts}

    # Northwind chain: decision-2026-09-12 superseded -> pricing-review (1 hop) & northwind-deal (2 hops)
    assert ("decision-2026-09-12", "pricing-review") in by_affected
    assert by_affected[("decision-2026-09-12", "pricing-review")].hops == 1
    assert ("decision-2026-09-12", "northwind-deal") in by_affected
    assert by_affected[("decision-2026-09-12", "northwind-deal")].hops == 2
    assert by_affected[("decision-2026-09-12", "northwind-deal")].alert_type == "STALE_DEPENDENCY"

    # Security, SOC2, Q4 launch, API v1 chains also propagated
    assert ("auth-token-rotation-rfc", "enterprise-security-audit") in by_affected
    assert ("vendor-dpa-2026-q2", "soc2-vendor-approval") in by_affected
    assert ("mobile-sync-architecture-v1", "q4-launch-freeze") in by_affected
    assert ("deprecation-timeline-draft", "api-v1-deprecation") in by_affected

    # Updating an upstream review also cascades STALE_DEPENDENCY to its dependent deal
    seeded_engine.update_record(
        "pricing-review",
        summary="Revised margin model with 85.4% floor",
        change_note="Infra COGS updated",
        propagate_stale=True,
        caller="founder",
    )
    updated_alerts = seeded_engine.list_freshness_alerts(caller="founder", status="open")
    assert any(
        a.trigger_record_id == "pricing-review"
        and a.affected_record_id == "northwind-deal"
        and a.alert_type == "STALE_DEPENDENCY"
        for a in updated_alerts
    )

    # Deterministic replay reproduces all propagated alerts identically
    replay = seeded_engine.rebuild_projections()
    assert replay.deterministic_match is True


# ------------------------------------------------------------------
# 4. 1-SQL Recursive Blocker Tracer & Benchmark Suite Tests
# ------------------------------------------------------------------


def test_single_sql_blocker_tracer_all_five_scenarios(seeded_engine: NativeContextEngine) -> None:
    expected = {
        "northwind-deal": ("decision-2026-09-12", "finance-sign-off"),
        "enterprise-security-audit": ("auth-token-rotation-rfc", "kms-key-ceremony"),
        "soc2-vendor-approval": ("vendor-dpa-2026-q2", "legal-redline-signoff"),
        "q4-launch-freeze": ("mobile-sync-architecture-v1", "load-test-certification"),
        "api-v1-deprecation": ("deprecation-timeline-draft", "sdk-v3-release-gate"),
    }
    for root_id, (superseded_id, terminal_id) in expected.items():
        res = seeded_engine.trace_blocker_chain(root_id, caller="founder")
        assert res.sql_queries_executed == 1
        assert superseded_id in res.superseded_nodes
        assert any(tb.record_id == terminal_id for tb in res.terminal_blockers)


def test_markdown_vs_native_benchmark_meets_efficiency_and_accuracy_targets(
    seeded_engine: NativeContextEngine,
) -> None:
    runner = BenchmarkRunner(engine=seeded_engine)
    report = runner.run_all(caller="founder")

    assert report.vault_document_count == 25
    assert report.scenario_count == 5
    assert report.native_accuracy_pct == 100.0
    assert report.naive_markdown_accuracy_pct == 0.0
    assert report.stale_error_reduction_pct == 100.0
    assert report.avg_native_turns == 1.0
    assert report.avg_markdown_turns == 6.0

    # Must prove >15x aggregate single-pass payload reduction and >60x cumulative context reduction
    assert report.avg_payload_reduction_x >= 15.0
    assert report.avg_cumulative_reduction_x >= 60.0

    for item in report.results:
        assert item.native_sql_queries == 1
        assert item.native_correct is True
        assert item.markdown_naive_correct is False
        assert item.markdown_diligent_correct is True
        assert item.payload_token_reduction_x >= 12.0
        assert item.cumulative_token_reduction_x >= 40.0

    md_out = format_benchmark_markdown(report)
    assert "Markdown Vault vs. Native SQLite Context Engine" in md_out
    assert "finance-sign-off" in md_out
    json_out = json.loads(format_benchmark_json(report))
    assert json_out["scenario_count"] == 5


def test_invalid_link_relation_rejected_without_mutating_event_log(
    seeded_engine: NativeContextEngine,
) -> None:
    before_events = int(seeded_engine.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
    with pytest.raises(ValueError, match="Unsupported relation"):
        seeded_engine.add_link(
            source_id="northwind-deal",
            target_id="pricing-review",
            relation="teleports_to",
            caller="founder",
        )
    after_events = int(seeded_engine.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
    assert after_events == before_events
    assert seeded_engine.verify_event_hash_chain() is True


def test_stale_alerts_fail_closed_when_trigger_is_founder_restricted(
    seeded_engine: NativeContextEngine,
) -> None:
    # Updating founder-only finance-sign-off cascades STALE_DEPENDENCY to decision-2026-10-02
    seeded_engine.update_record(
        "finance-sign-off",
        summary="CFO requested additional runway check",
        change_note="Board covenant check",
        propagate_stale=True,
        caller="founder",
    )
    founder_alerts = seeded_engine.list_freshness_alerts(caller="founder", status="open")
    contractor_alerts = seeded_engine.list_freshness_alerts(caller="contractor", status="open")

    assert any(a.trigger_record_id == "finance-sign-off" for a in founder_alerts)
    # Contractor MUST NOT see any alert whose trigger_record_id is founder-only
    assert all(a.trigger_record_id != "finance-sign-off" for a in contractor_alerts)


def test_kanban_html_artifact_contractor_fail_closed_redaction(
    seeded_engine: NativeContextEngine,
) -> None:
    runtime = ArtifactRuntime(seeded_engine)
    kanban_contractor = runtime.render_view("kanban_dependency_cards", caller="contractor")
    assert kanban_contractor.schema_version == "native.html.artifact.v2"
    assert kanban_contractor.envelopes["launch_blockers"].record_count == 22
    for forbidden_id in ("finance-sign-off", "kms-key-ceremony", "legal-redline-signoff"):
        assert forbidden_id not in kanban_contractor.document_export
        assert all(
            c["record_id"] != forbidden_id
            for col in kanban_contractor.view_model["columns"]
            for c in col["cards"]
        )


def test_cli_subcommands_benchmark_replay_and_export(capsys: pytest.CaptureFixture[str]) -> None:
    from native_lens.cli import main as cli_main

    assert cli_main(["benchmark", "--format", "json"]) == 0
    bench_payload = json.loads(capsys.readouterr().out)
    assert bench_payload["scenario_count"] == 5
    assert bench_payload["avg_payload_reduction_x"] >= 15.0

    assert cli_main(["replay-check"]) == 0
    replay_payload = json.loads(capsys.readouterr().out)
    assert replay_payload["replay_verification"]["deterministic_match"] is True
    assert replay_payload["replay_verification"]["chain_integrity_valid"] is True

    assert cli_main(["export-artifact", "--view", "compact_decision_table", "--caller", "contractor"]) == 0
    mdx_out = capsys.readouterr().out
    assert "schema: native.mdx.artifact.v2" in mdx_out
    assert 'records: 22' in mdx_out


# ------------------------------------------------------------------
# 5. Malleable Artifact Runtime Validator & Dual-View Renderer Tests
# ------------------------------------------------------------------


def test_malleable_artifact_dual_views_and_fail_closed_contract(
    seeded_engine: NativeContextEngine,
) -> None:
    runtime = ArtifactRuntime(seeded_engine)

    # View A: Compact Decision Table (native.mdx.artifact.v2)
    table_art = runtime.render_view("compact_decision_table", caller="founder")
    assert table_art.schema_version == "native.mdx.artifact.v2"
    assert table_art.fallback_surface is None
    assert table_art.envelopes["launch_blockers"].envelope == "native.collection-envelope.v1"
    assert table_art.envelopes["launch_blockers"].record_count == 25
    assert "kind: artifact" in table_art.document_export
    assert "schema: native.mdx.artifact.v2" in table_art.document_export

    # View B: Kanban Dependency Cards (native.html.artifact.v2) over the EXACT SAME collection
    kanban_art = runtime.render_view("kanban_dependency_cards", caller="founder")
    assert kanban_art.schema_version == "native.html.artifact.v2"
    assert kanban_art.fallback_surface is None
    assert kanban_art.envelopes["launch_blockers"].record_count == 25
    assert "application/vnd.native.artifact+json" in kanban_art.document_export
    assert kanban_art.view_model["layout"] == "kanban_dependency_cards"

    # Fail-closed ACL filtering inside artifacts for contractor
    contractor_art = runtime.render_view("compact_decision_table", caller="contractor")
    assert contractor_art.envelopes["launch_blockers"].record_count == 22
    rendered_ids = {r["record_id"] for r in contractor_art.view_model["rows"]}
    assert "finance-sign-off" not in rendered_ids
    assert "kms-key-ceremony" not in rendered_ids
    assert "legal-redline-signoff" not in rendered_ids

    # Anonymous caller fails closed with NO fallback surface
    with pytest.raises(ArtifactAccessDeniedError) as exc_info:
        runtime.render_view("compact_decision_table", caller="anonymous")
    assert exc_info.value.code == "COLLECTION_ACCESS_DENIED"
    assert exc_info.value.fallback_surface is None

    # Forbidden capability rejected fail-closed
    bad_cap_manifest = {
        "schema": "native.html.artifact.v2",
        "artifact_id": "bad-widget",
        "title": "Hostile Widget",
        "view_type": "kanban_dependency_cards",
        "inputs": [
            {
                "name": "launch_blockers",
                "envelope": "native.collection-envelope.v1",
                "collection": "launch_blockers",
                "required": True,
                "expose_to_root": True,
            }
        ],
        "capability_requests": ["input.read", "shell.exec"],
    }
    with pytest.raises(ArtifactValidationError) as cap_err:
        runtime.validate_manifest(bad_cap_manifest)
    assert cap_err.value.code == "CAPABILITY_DENIED_FAIL_CLOSED"
    assert cap_err.value.fallback_surface is None

    # Missing input.read rejected fail-closed
    missing_read_manifest = {**bad_cap_manifest, "capability_requests": ["navigation.record.user_gesture"]}
    with pytest.raises(ArtifactValidationError) as read_err:
        runtime.validate_manifest(missing_read_manifest)
    assert read_err.value.code == "MISSING_INPUT_READ_CAPABILITY"

    # Invalid schema version rejected fail-closed
    bad_schema_manifest = {
        **bad_cap_manifest,
        "schema": "native.mdx.artifact.v1",
        "capability_requests": ["input.read"],
    }
    with pytest.raises(ArtifactValidationError) as schema_err:
        runtime.validate_manifest(bad_schema_manifest)
    assert schema_err.value.code == "UNSUPPORTED_ARTIFACT_SCHEMA"

    # Invalid envelope rejected fail-closed
    bad_env_manifest = {
        **bad_cap_manifest,
        "capability_requests": ["input.read"],
        "inputs": [
            {
                "name": "launch_blockers",
                "envelope": "raw.untyped.v0",
                "collection": "launch_blockers",
                "required": True,
                "expose_to_root": True,
            }
        ],
    }
    with pytest.raises(ArtifactValidationError) as env_err:
        runtime.validate_manifest(bad_env_manifest)
    assert env_err.value.code == "INVALID_INPUT_ENVELOPE"


# ------------------------------------------------------------------
# 6. FastAPI End-to-End Integration Tests
# ------------------------------------------------------------------


def test_fastapi_workbench_endpoints_end_to_end(tmp_path: Path) -> None:
    app = create_app(db_path=tmp_path / "api_test.sqlite3")
    client = TestClient(app)

    # Root HTML workbench serves cleanly
    r_home = client.get("/")
    assert r_home.status_code == 200
    assert "Native Context Lens" in r_home.text

    # Health & WAL verification
    r_health = client.get("/api/health")
    assert r_health.status_code == 200
    health = r_health.json()
    assert health["status"] == "ok"
    assert health["journal_mode"].lower() == "wal"
    assert health["chain_integrity_valid"] is True

    # Personas & Benchmark scenarios
    assert len(client.get("/api/personas").json()["personas"]) == 4
    assert len(client.get("/api/benchmark/scenarios").json()["scenarios"]) == 5

    # Run all 5 benchmarks via REST API
    r_bench = client.post("/api/benchmark/run", json={"scenario_id": None, "caller": "founder"})
    assert r_bench.status_code == 200
    rep = r_bench.json()["report"]
    assert rep["scenario_count"] == 5
    assert rep["avg_payload_reduction_x"] >= 15.0
    assert rep["native_accuracy_pct"] == 100.0

    # Governed records ACL via REST
    assert client.get("/api/records?caller=founder").json()["count"] == 25
    assert client.get("/api/records?caller=contractor").json()["count"] == 22
    assert client.get("/api/records?caller=anonymous").json()["count"] == 0

    # 1-SQL trace endpoint
    r_trace = client.get("/api/trace/northwind-deal?caller=founder")
    assert r_trace.status_code == 200
    assert r_trace.json()["sql_queries_executed"] == 1
    assert r_trace.json()["terminal_blockers"][0]["record_id"] == "finance-sign-off"

    # Artifact rendering (both views + fail-closed anonymous 403)
    r_tbl = client.get("/api/artifacts/render?view=compact_decision_table&caller=contractor")
    assert r_tbl.status_code == 200
    assert r_tbl.json()["envelopes"]["launch_blockers"]["record_count"] == 22

    r_kbn = client.get("/api/artifacts/render?view=kanban_dependency_cards&caller=founder")
    assert r_kbn.status_code == 200
    assert r_kbn.json()["envelopes"]["launch_blockers"]["record_count"] == 25

    r_anon = client.get("/api/artifacts/render?view=compact_decision_table&caller=anonymous")
    assert r_anon.status_code == 403
    assert r_anon.json()["error_code"] == "COLLECTION_ACCESS_DENIED"
    assert r_anon.json()["fallback_surface"] is None

    # Artifact manifest red-team endpoint
    r_val = client.post(
        "/api/artifacts/validate",
        json={
            "manifest": {
                "schema": "native.html.artifact.v2",
                "artifact_id": "rogue",
                "title": "Rogue",
                "view_type": "kanban_dependency_cards",
                "inputs": [
                    {
                        "name": "launch_blockers",
                        "envelope": "native.collection-envelope.v1",
                        "collection": "launch_blockers",
                        "required": True,
                        "expose_to_root": True,
                    }
                ],
                "capability_requests": ["input.read", "shell.exec"],
            }
        },
    )
    assert r_val.status_code == 422
    assert r_val.json()["error_code"] == "CAPABILITY_DENIED_FAIL_CLOSED"
    assert r_val.json()["fallback_surface"] is None

    # Interactive supersede: contractor blocked 403, founder succeeds + propagates alerts
    sup_body = {
        "old_record_id": "decision-2026-10-02",
        "new_title": "Decision 2026-10-09: Revised 20% Floor",
        "new_summary": "Board updated strategic floor to 20% for 3-year cash prepay.",
        "reason": "Updated margin model",
        "caller": "contractor",
    }
    assert client.post("/api/actions/supersede", json=sup_body).status_code == 403

    sup_body["caller"] = "founder"
    r_sup = client.post("/api/actions/supersede", json=sup_body)
    assert r_sup.status_code == 200
    assert r_sup.json()["ok"] is True

    # Deterministic replay endpoint after mutation
    r_rep = client.post("/api/engine/replay")
    assert r_rep.status_code == 200
    assert r_rep.json()["deterministic_match"] is True
    assert r_rep.json()["chain_integrity_valid"] is True

    # Event log endpoint + reset endpoint
    r_ev = client.get("/api/events?limit=10")
    assert r_ev.status_code == 200
    assert r_ev.json()["chain_integrity_valid"] is True
    assert len(r_ev.json()["events"]) == 10

    r_rst = client.post("/api/actions/reset")
    assert r_rst.status_code == 200
    assert r_rst.json()["ok"] is True
