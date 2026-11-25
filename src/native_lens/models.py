"""Pydantic v2 domain, authorization, benchmark, and malleable artifact schemas."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CallerContext(BaseModel):
    """Explicit caller identity and roles passed into every governed operation."""

    caller_id: str = Field(..., min_length=1)
    display_name: str = ""
    roles: list[str] = Field(default_factory=list)

    @property
    def principals(self) -> list[str]:
        seen: list[str] = []
        for p in [f"caller:{self.caller_id}", *[f"role:{r}" for r in self.roles]]:
            if p not in seen:
                seen.append(p)
        return seen


class RecordModel(BaseModel):
    """Projected record state (derived strictly from authoritative events)."""

    record_id: str
    collection: str
    kind: str
    title: str
    status: str
    owner: str
    summary: str
    body: str = ""
    superseded_by: str | None = None
    version: int = 1
    updated_at: str
    source_path: str | None = None
    facets: dict[str, list[str]] = Field(default_factory=dict)
    open_stale_alerts: int = 0


class LinkModel(BaseModel):
    """Projected typed edge between two records."""

    link_id: str
    source_id: str
    target_id: str
    relation: Literal["blocks", "supersedes", "depends_on", "references", "waiting_on"]
    note: str = ""
    created_at: str


class FreshnessAlert(BaseModel):
    """Projected stale-context alert emitted atomically on upstream supersession/update."""

    alert_id: str
    affected_record_id: str
    affected_title: str = ""
    trigger_record_id: str
    trigger_title: str = ""
    replacement_record_id: str | None = None
    replacement_title: str | None = None
    alert_type: str
    severity: Literal["critical", "high", "medium"]
    hops: int
    path: list[str] = Field(default_factory=list)
    message: str
    status: Literal["open", "resolved"] = "open"
    created_at: str


class EventEntry(BaseModel):
    """Single immutable row from the authoritative append-only events log."""

    seq: int
    event_id: str
    event_type: str
    aggregate_id: str
    actor_id: str
    payload: dict[str, Any]
    created_at: str
    prev_hash: str
    event_hash: str


class BlockerHop(BaseModel):
    """One node in a single-SQL recursive blocker trace."""

    hop: int
    record_id: str
    title: str
    kind: str
    collection: str
    status: str
    owner: str
    summary: str
    via_relation: str
    from_record_id: str | None = None
    superseded_by: str | None = None
    open_stale_alerts: int = 0


class BlockerChainResult(BaseModel):
    """Result of the 1-SQL-query recursive blocker tracer."""

    root_record_id: str
    caller_id: str
    sql_queries_executed: int = 1
    elapsed_ms: float
    chain: list[BlockerHop] = Field(default_factory=list)
    terminal_blockers: list[BlockerHop] = Field(default_factory=list)
    superseded_nodes: list[str] = Field(default_factory=list)
    compact_payload_json: str = ""
    estimated_tokens: int = 0


class ReplayVerification(BaseModel):
    """Result of dropping all projections and replaying from authoritative events."""

    events_replayed: int
    before_digest: str
    after_digest: str
    deterministic_match: bool
    chain_integrity_valid: bool
    elapsed_ms: float


# --- Benchmark Models ---


class BenchmarkTurn(BaseModel):
    """One turn taken by the baseline Markdown wikilink agent."""

    turn: int
    action: str
    detail: str
    files_read: list[str] = Field(default_factory=list)
    payload_tokens: int
    cumulative_context_tokens: int
    hit_stale_trap: bool = False


class ScenarioSpec(BaseModel):
    """Definition of one multi-hop company benchmark question."""

    scenario_id: str
    title: str
    question: str
    root_record_id: str
    expected_terminal_blocker_id: str
    expected_superseded_id: str
    expected_active_decision_id: str
    search_keywords: list[str]


class ScenarioBenchmarkResult(BaseModel):
    """Head-to-head result for a single scenario."""

    scenario: ScenarioSpec
    markdown_turns: int
    markdown_files_read: list[str]
    markdown_payload_tokens: int
    markdown_cumulative_tokens: int
    markdown_trace: list[BenchmarkTurn]
    markdown_naive_answer_id: str
    markdown_naive_correct: bool
    markdown_diligent_answer_id: str
    markdown_diligent_correct: bool
    markdown_simulated_seconds: float
    native_sql_queries: int
    native_turns: int
    native_payload_tokens: int
    native_elapsed_ms: float
    native_answer_id: str
    native_correct: bool
    native_chain: list[BlockerHop]
    payload_token_reduction_x: float
    cumulative_token_reduction_x: float
    tokens_saved_payload: int
    tokens_saved_cumulative: int


class BenchmarkReport(BaseModel):
    """Aggregate report across all benchmark scenarios."""

    vault_document_count: int
    vault_total_tokens: int
    scenario_count: int
    results: list[ScenarioBenchmarkResult]
    total_markdown_payload_tokens: int
    total_markdown_cumulative_tokens: int
    total_native_payload_tokens: int
    avg_payload_reduction_x: float
    avg_cumulative_reduction_x: float
    avg_markdown_turns: float
    avg_native_turns: float
    naive_markdown_accuracy_pct: float
    native_accuracy_pct: float
    stale_error_reduction_pct: float


# --- Malleable Artifact Models ---


class ArtifactInputBinding(BaseModel):
    """Explicit input binding conforming to native.collection-envelope.v1."""

    name: str = Field(..., min_length=1)
    envelope: str
    collection: str = Field(..., min_length=1)
    required: bool = True
    expose_to_root: bool = True


class ArtifactManifest(BaseModel):
    """Contract for native.mdx.artifact.v2 and native.html.artifact.v2."""

    schema_version: str = Field(..., alias="schema")
    artifact_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    view_type: Literal["compact_decision_table", "kanban_dependency_cards"]
    inputs: list[ArtifactInputBinding] = Field(default_factory=list)
    capability_requests: list[str] = Field(default_factory=list)
    description: str = ""

    model_config = {"populate_by_name": True}


class CollectionEnvelopeV1(BaseModel):
    """Governed data envelope passed into an authorized artifact surface."""

    envelope: Literal["native.collection-envelope.v1"] = "native.collection-envelope.v1"
    collection: str
    caller_id: str
    record_count: int
    records: list[dict[str, Any]]
    links: list[dict[str, Any]]
    freshness_alerts: list[dict[str, Any]]


class RenderedArtifact(BaseModel):
    """Validated and rendered artifact output plus Native Document kind:artifact source."""

    artifact_id: str
    schema_version: str
    title: str
    view_type: str
    caller_id: str
    granted_capabilities: list[str]
    envelopes: dict[str, CollectionEnvelopeV1]
    view_model: dict[str, Any]
    document_export: str
    export_format: Literal["mdx", "html"]
    fallback_surface: None = None
