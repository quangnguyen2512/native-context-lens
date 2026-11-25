"""FastAPI backend for the native-context-lens interactive workbench."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from native_lens.artifacts import (
    ArtifactAccessDeniedError,
    ArtifactRuntime,
    ArtifactValidationError,
)
from native_lens.benchmark import BenchmarkRunner, format_benchmark_markdown
from native_lens.engine import (
    DEFAULT_PERSONAS,
    AuthorizationError,
    NativeContextEngine,
    RecordNotFoundError,
)
from native_lens.vault import default_vault_dir, load_vault_into_engine


class BenchmarkRunRequest(BaseModel):
    scenario_id: str | None = None
    caller: str = "founder"


class SupersedeRequest(BaseModel):
    old_record_id: str = Field(..., min_length=1)
    new_record_id: str | None = None
    new_title: str = Field(..., min_length=3)
    new_summary: str = Field(..., min_length=5)
    owner: str = "George (Founder)"
    reason: str = "Superseded via interactive Native Context Lens workbench"
    caller: str = "founder"


class ArtifactValidateRequest(BaseModel):
    manifest: dict[str, Any]


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48] or "decision-rev"


def create_app(
    db_path: str | Path | None = None,
    vault_dir: Path | None = None,
) -> FastAPI:
    resolved_vault = vault_dir or default_vault_dir()
    if db_path is None:
        tmp_dir = Path(tempfile.gettempdir()) / "native_context_lens"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        resolved_db: str | Path = tmp_dir / "workstation.sqlite3"
        # Start fresh from the authoritative vault on boot
        for suffix in ("", "-wal", "-shm"):
            p = Path(f"{resolved_db}{suffix}")
            if p.exists():
                p.unlink()
    else:
        resolved_db = db_path

    state: dict[str, Any] = {}

    def _bootstrap() -> None:
        if "engine" in state:
            try:
                state["engine"].close()
            except Exception:
                pass
        if str(resolved_db) != ":memory:":
            for suffix in ("", "-wal", "-shm"):
                p = Path(f"{resolved_db}{suffix}")
                if p.exists():
                    p.unlink()
        engine = NativeContextEngine(resolved_db)
        stats = load_vault_into_engine(engine, resolved_vault)
        state["engine"] = engine
        state["runtime"] = ArtifactRuntime(engine)
        state["runner"] = BenchmarkRunner(engine=engine, vault_dir=resolved_vault)
        state["vault_stats"] = stats

    _bootstrap()

    app = FastAPI(
        title="Native Context Lens",
        version="0.1.0",
        description="Governed Event-Sourced Context Engine, Benchmark Suite & Malleable Artifact Workbench",
    )

    static_dir = Path(__file__).resolve().parent / "static"

    @app.get("/", include_in_schema=False)
    def serve_workbench() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        engine: NativeContextEngine = state["engine"]
        events_count = int(engine.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        wal_mode = str(engine.conn.execute("PRAGMA journal_mode;").fetchone()[0])
        return {
            "status": "ok",
            "db_path": engine.db_path,
            "journal_mode": wal_mode,
            "events_count": events_count,
            "vault_stats": state["vault_stats"],
            "projection_digest": engine.compute_projection_digest(),
            "chain_integrity_valid": engine.verify_event_hash_chain(),
        }

    @app.get("/api/personas")
    def list_personas() -> dict[str, Any]:
        descriptions = {
            "founder": "Full governance access: sees all 25 records including founder-only CFO sign-off & HSM ceremony.",
            "engineer": "Core member access: sees 23 records; founder-only records fail closed.",
            "contractor": "External contractor ACL: sees 22 public records; founder & internal legal sign-offs hidden fail-closed; read-only.",
            "anonymous": "Unauthenticated caller: zero permissions; all queries return 0 rows and required artifacts fail closed (403).",
        }
        return {
            "personas": [
                {
                    "key": key,
                    "caller_id": ctx.caller_id,
                    "display_name": ctx.display_name,
                    "roles": ctx.roles,
                    "description": descriptions.get(key, ""),
                }
                for key, ctx in DEFAULT_PERSONAS.items()
            ]
        }

    @app.get("/api/benchmark/scenarios")
    def list_scenarios() -> dict[str, Any]:
        runner: BenchmarkRunner = state["runner"]
        return {"scenarios": [s.model_dump() for s in runner.list_scenarios()]}

    @app.post("/api/benchmark/run")
    def run_benchmark(req: BenchmarkRunRequest) -> dict[str, Any]:
        runner: BenchmarkRunner = state["runner"]
        try:
            report = runner.run_all(scenario_id=req.scenario_id, caller=req.caller)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "report": report.model_dump(),
            "markdown": format_benchmark_markdown(report),
        }

    @app.get("/api/records")
    def get_records(
        caller: str = Query("founder"),
        collection: str | None = Query(None),
        status: str | None = Query(None),
        kind: str | None = Query(None),
    ) -> dict[str, Any]:
        engine: NativeContextEngine = state["engine"]
        recs = engine.query_records(
            caller=caller, collection=collection, status=status, kind=kind
        )
        return {
            "caller": engine.resolve_caller(caller).model_dump(),
            "count": len(recs),
            "records": [r.model_dump() for r in recs],
        }

    @app.get("/api/trace/{record_id}")
    def trace_record(record_id: str, caller: str = Query("founder")) -> dict[str, Any]:
        engine: NativeContextEngine = state["engine"]
        result = engine.trace_blocker_chain(record_id=record_id, caller=caller)
        return result.model_dump()

    @app.get("/api/alerts")
    def get_alerts(
        caller: str = Query("founder"),
        status: str | None = Query("open"),
    ) -> dict[str, Any]:
        engine: NativeContextEngine = state["engine"]
        alerts = engine.list_freshness_alerts(caller=caller, status=status)
        return {
            "caller_id": engine.resolve_caller(caller).caller_id,
            "count": len(alerts),
            "alerts": [a.model_dump() for a in alerts],
        }

    @app.post("/api/actions/supersede")
    def supersede_decision(req: SupersedeRequest) -> dict[str, Any]:
        engine: NativeContextEngine = state["engine"]
        try:
            old_rec = engine.get_record(req.old_record_id, caller=req.caller)
        except RecordNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        new_id = req.new_record_id or f"{req.old_record_id}-rev-{_slugify(req.new_title)[:14]}"
        created_events = []
        try:
            # Create the new replacement decision if it doesn't exist yet
            try:
                engine.get_record(new_id, caller=req.caller)
            except RecordNotFoundError:
                ev_create = engine.create_record(
                    record_id=new_id,
                    collection=old_rec.collection,
                    kind=old_rec.kind,
                    title=req.new_title,
                    status="active",
                    owner=req.owner,
                    summary=req.new_summary,
                    body=f"# {req.new_title}\n\nSupersedes [[{old_rec.record_id}]].\n\n{req.new_summary}",
                    facets=old_rec.facets,
                    caller=req.caller,
                )
                created_events.append(ev_create.model_dump())

            ev_sup = engine.supersede_record(
                old_record_id=req.old_record_id,
                new_record_id=new_id,
                reason=req.reason,
                caller=req.caller,
            )
            created_events.append(ev_sup.model_dump())
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except RecordNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        alerts = engine.list_freshness_alerts(caller=req.caller, status="open")
        new_alerts = [a.model_dump() for a in alerts if a.trigger_record_id == req.old_record_id]
        return {
            "ok": True,
            "old_record_id": req.old_record_id,
            "new_record_id": new_id,
            "events_appended": created_events,
            "propagated_alerts": new_alerts,
            "total_open_alerts": len(alerts),
            "projection_digest": engine.compute_projection_digest(),
        }

    @app.post("/api/actions/reset")
    def reset_demo() -> dict[str, Any]:
        _bootstrap()
        engine: NativeContextEngine = state["engine"]
        return {
            "ok": True,
            "message": "Workspace reset to authoritative 25-document baseline vault.",
            "projection_digest": engine.compute_projection_digest(),
        }

    @app.get("/api/artifacts/render")
    def render_artifact(
        view: str = Query("compact_decision_table"),
        caller: str = Query("founder"),
    ) -> JSONResponse:
        runtime: ArtifactRuntime = state["runtime"]
        try:
            rendered = runtime.render_view(view, caller=caller)
            return JSONResponse(status_code=200, content=rendered.model_dump())
        except ArtifactAccessDeniedError as exc:
            return JSONResponse(status_code=403, content=exc.to_diagnostic())
        except ArtifactValidationError as exc:
            return JSONResponse(status_code=422, content=exc.to_diagnostic())

    @app.post("/api/artifacts/validate")
    def validate_artifact_manifest(req: ArtifactValidateRequest) -> JSONResponse:
        runtime: ArtifactRuntime = state["runtime"]
        try:
            validated = runtime.validate_manifest(req.manifest)
            return JSONResponse(
                status_code=200,
                content={
                    "ok": True,
                    "manifest": validated.model_dump(by_alias=True),
                    "fallback_surface": None,
                },
            )
        except ArtifactValidationError as exc:
            return JSONResponse(status_code=422, content=exc.to_diagnostic())

    @app.get("/api/events")
    def list_events(limit: int = Query(60, ge=1, le=500)) -> dict[str, Any]:
        engine: NativeContextEngine = state["engine"]
        events = engine.list_events(limit=limit)
        total = int(engine.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        return {
            "total_events": total,
            "chain_integrity_valid": engine.verify_event_hash_chain(),
            "projection_digest": engine.compute_projection_digest(),
            "events": [e.model_dump() for e in events],
        }

    @app.post("/api/engine/replay")
    def replay_engine() -> dict[str, Any]:
        engine: NativeContextEngine = state["engine"]
        verification = engine.rebuild_projections()
        return verification.model_dump()

    app.state.native_lens = state
    return app


app = create_app()
