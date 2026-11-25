"""Malleable Artifact Runtime Validator, Fail-Closed Host Authority & Dual-View Renderer.

Implements the documented `withnative/native` malleable artifact separation:
  - Durable data: governed SQLite collections delivered via `native.collection-envelope.v1`
  - Authored presentation: `native.mdx.artifact.v2` or `native.html.artifact.v2`
  - Host authority: explicit `inputs` and `capability_requests` validation;
    failures NEVER select a fallback surface (`fallback_surface = None`), and
    unauthorized records/collections fail closed at the engine ACL boundary.
"""

from __future__ import annotations

import html
import json
from typing import Any

from native_lens.engine import NativeContextEngine
from native_lens.models import (
    ArtifactInputBinding,
    ArtifactManifest,
    CallerContext,
    CollectionEnvelopeV1,
    RenderedArtifact,
)

SUPPORTED_ARTIFACT_SCHEMAS = frozenset(
    {
        "native.mdx.artifact.v2",
        "native.html.artifact.v2",
    }
)
REQUIRED_ENVELOPE_SCHEMA = "native.collection-envelope.v1"
ALLOWED_HOST_CAPABILITIES = frozenset(
    {
        "input.read",
        "navigation.record.user_gesture",
        "view.state.ephemeral",
    }
)


class ArtifactRuntimeError(RuntimeError):
    """Base fail-closed artifact runtime error (never selects a fallback surface)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.fallback_surface = None

    def to_diagnostic(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error_code": self.code,
            "detail": self.message,
            "fallback_surface": None,
        }


class ArtifactValidationError(ArtifactRuntimeError):
    """Raised when an artifact manifest violates schema, input, or capability rules."""


class ArtifactAccessDeniedError(ArtifactRuntimeError):
    """Raised when a caller lacks authorization for a required governed collection."""


BUILTIN_MANIFESTS: dict[str, ArtifactManifest] = {
    "compact_decision_table": ArtifactManifest(
        schema="native.mdx.artifact.v2",
        artifact_id="launch-blockers-decision-table",
        title="Launch Blockers — Compact Decision Table",
        view_type="compact_decision_table",
        description="High-density executive decision & freshness table over governed launch_blockers collection.",
        inputs=[
            ArtifactInputBinding(
                name="launch_blockers",
                envelope="native.collection-envelope.v1",
                collection="launch_blockers",
                required=True,
                expose_to_root=True,
            )
        ],
        capability_requests=["input.read", "navigation.record.user_gesture"],
    ),
    "kanban_dependency_cards": ArtifactManifest(
        schema="native.html.artifact.v2",
        artifact_id="launch-blockers-kanban-graph",
        title="Launch Blockers — Kanban & Dependency Graph Cards",
        view_type="kanban_dependency_cards",
        description="Status-column Kanban cards with live dependency links and stale-context badges over launch_blockers.",
        inputs=[
            ArtifactInputBinding(
                name="launch_blockers",
                envelope="native.collection-envelope.v1",
                collection="launch_blockers",
                required=True,
                expose_to_root=True,
            )
        ],
        capability_requests=["input.read", "navigation.record.user_gesture", "view.state.ephemeral"],
    ),
}


class ArtifactRuntime:
    """Validates v2 artifact manifests and renders dual views over governed collections."""

    def __init__(self, engine: NativeContextEngine) -> None:
        self.engine = engine

    def validate_manifest(self, manifest: ArtifactManifest | dict[str, Any]) -> ArtifactManifest:
        """Strictly validate a v2 manifest; fail closed with zero fallback surface."""
        try:
            parsed = (
                manifest
                if isinstance(manifest, ArtifactManifest)
                else ArtifactManifest.model_validate(manifest)
            )
        except Exception as exc:
            raise ArtifactValidationError("ARTIFACT_SCHEMA_INVALID", str(exc)) from exc

        if parsed.schema_version not in SUPPORTED_ARTIFACT_SCHEMAS:
            raise ArtifactValidationError(
                "UNSUPPORTED_ARTIFACT_SCHEMA",
                f"Schema '{parsed.schema_version}' is not supported. "
                f"Expected one of {sorted(SUPPORTED_ARTIFACT_SCHEMAS)}.",
            )

        if not parsed.inputs:
            raise ArtifactValidationError(
                "MISSING_DECLARED_INPUTS",
                "Artifact must declare at least one governed input binding.",
            )

        seen_ports: set[str] = set()
        for binding in parsed.inputs:
            if binding.name in seen_ports:
                raise ArtifactValidationError(
                    "DUPLICATE_INPUT_PORT",
                    f"Duplicate input port '{binding.name}' declared in manifest.",
                )
            seen_ports.add(binding.name)
            if binding.envelope != REQUIRED_ENVELOPE_SCHEMA:
                raise ArtifactValidationError(
                    "INVALID_INPUT_ENVELOPE",
                    f"Input '{binding.name}' declared envelope '{binding.envelope}', "
                    f"expected '{REQUIRED_ENVELOPE_SCHEMA}'.",
                )
            if not binding.expose_to_root:
                raise ArtifactValidationError(
                    "UNEXPOSED_ROOT_INPUT",
                    f"Input '{binding.name}' must explicitly set expose_to_root=true for root rendering.",
                )

        # Capability host authority check
        if not parsed.capability_requests:
            raise ArtifactValidationError(
                "MISSING_CAPABILITY_REQUESTS",
                "Artifact must explicitly declare capability_requests (at minimum 'input.read').",
            )

        unknown_caps = [
            c for c in parsed.capability_requests if c not in ALLOWED_HOST_CAPABILITIES
        ]
        if unknown_caps:
            raise ArtifactValidationError(
                "CAPABILITY_DENIED_FAIL_CLOSED",
                f"Forbidden or unknown capability_requests rejected fail-closed: {unknown_caps}. "
                f"Allowed host capabilities: {sorted(ALLOWED_HOST_CAPABILITIES)}.",
            )

        if "input.read" not in parsed.capability_requests:
            raise ArtifactValidationError(
                "MISSING_INPUT_READ_CAPABILITY",
                "Artifacts declaring governed inputs MUST request the 'input.read' capability.",
            )

        return parsed

    def build_envelope(
        self,
        binding: ArtifactInputBinding,
        caller: CallerContext | str,
    ) -> CollectionEnvelopeV1:
        """Assemble a `native.collection-envelope.v1` filtered fail-closed at the SQLite boundary."""
        ctx = self.engine.resolve_caller(caller)
        has_collection_access = self.engine.can_access_collection(binding.collection, ctx)
        records = self.engine.query_records(caller=ctx, collection=binding.collection)

        if binding.required and not has_collection_access and not records:
            raise ArtifactAccessDeniedError(
                "COLLECTION_ACCESS_DENIED",
                f"Caller '{ctx.caller_id}' is not authorized to read required collection "
                f"'{binding.collection}'. Failing closed with no fallback surface.",
            )

        authorized_ids = [r.record_id for r in records]
        links = (
            self.engine.list_links(caller=ctx, record_ids=authorized_ids)
            if authorized_ids
            else []
        )
        alerts = self.engine.list_freshness_alerts(
            caller=ctx, status="open", collection=binding.collection
        )

        # Strip body text from envelope records to keep malleable surface payloads lean
        compact_records = [
            {
                "record_id": r.record_id,
                "collection": r.collection,
                "kind": r.kind,
                "title": r.title,
                "status": r.status,
                "owner": r.owner,
                "summary": r.summary,
                "superseded_by": r.superseded_by,
                "version": r.version,
                "updated_at": r.updated_at,
                "facets": r.facets,
                "open_stale_alerts": r.open_stale_alerts,
            }
            for r in records
        ]

        return CollectionEnvelopeV1(
            collection=binding.collection,
            caller_id=ctx.caller_id,
            record_count=len(compact_records),
            records=compact_records,
            links=[l.model_dump() for l in links],
            freshness_alerts=[a.model_dump() for a in alerts],
        )

    def render_view(
        self,
        view_type_or_manifest: str | ArtifactManifest | dict[str, Any],
        caller: CallerContext | str = "founder",
    ) -> RenderedArtifact:
        """Validate manifest, enforce ACLs, render structured view model + exportable Native artifact."""
        if isinstance(view_type_or_manifest, str):
            if view_type_or_manifest not in BUILTIN_MANIFESTS:
                raise ArtifactValidationError(
                    "UNKNOWN_ARTIFACT_VIEW",
                    f"Unknown artifact view '{view_type_or_manifest}'. "
                    f"Available: {sorted(BUILTIN_MANIFESTS.keys())}.",
                )
            manifest = self.validate_manifest(BUILTIN_MANIFESTS[view_type_or_manifest])
        else:
            manifest = self.validate_manifest(view_type_or_manifest)

        ctx = self.engine.resolve_caller(caller)
        envelopes: dict[str, CollectionEnvelopeV1] = {}
        for binding in manifest.inputs:
            envelopes[binding.name] = self.build_envelope(binding, ctx)

        primary_port = manifest.inputs[0].name
        primary_env = envelopes[primary_port]

        if manifest.view_type == "compact_decision_table":
            view_model = self._build_decision_table_model(primary_env)
            export_doc = self._export_mdx_document(manifest, primary_port, primary_env)
            export_fmt: str = "mdx"
        else:
            view_model = self._build_kanban_graph_model(primary_env)
            export_doc = self._export_html_document(manifest, primary_port, primary_env, view_model)
            export_fmt = "html"

        return RenderedArtifact(
            artifact_id=manifest.artifact_id,
            schema_version=manifest.schema_version,
            title=manifest.title,
            view_type=manifest.view_type,
            caller_id=ctx.caller_id,
            granted_capabilities=list(manifest.capability_requests),
            envelopes=envelopes,
            view_model=view_model,
            document_export=export_doc,
            export_format=export_fmt,  # type: ignore[arg-type]
            fallback_surface=None,
        )

    def _build_decision_table_model(self, env: CollectionEnvelopeV1) -> dict[str, Any]:
        links_by_src: dict[str, list[dict[str, Any]]] = {}
        for lnk in env.links:
            links_by_src.setdefault(lnk["source_id"], []).append(lnk)

        rows = []
        for rec in env.records:
            outgoing = [
                f"{l['relation']} -> {l['target_id']}"
                for l in links_by_src.get(rec["record_id"], [])
            ]
            track = (rec.get("facets", {}).get("track") or ["general"])[0]
            rows.append(
                {
                    "record_id": rec["record_id"],
                    "track": track,
                    "kind": rec["kind"],
                    "title": rec["title"],
                    "status": rec["status"],
                    "owner": rec["owner"],
                    "superseded_by": rec["superseded_by"],
                    "open_stale_alerts": rec["open_stale_alerts"],
                    "outgoing_links": outgoing,
                    "summary": rec["summary"],
                }
            )
        return {
            "layout": "compact_decision_table",
            "columns": ["record_id", "track", "kind", "status", "owner", "stale_alerts", "links"],
            "total_rows": len(rows),
            "stale_count": sum(1 for r in rows if r["open_stale_alerts"] > 0),
            "superseded_count": sum(1 for r in rows if r["status"] == "superseded"),
            "rows": rows,
        }

    def _build_kanban_graph_model(self, env: CollectionEnvelopeV1) -> dict[str, Any]:
        column_order = [
            ("blocked", "Blocked / Waiting"),
            ("pending_signoff", "Pending Executive Sign-Off"),
            ("superseded", "Superseded (Historical)"),
            ("active", "Active / Clear"),
            ("resolved", "Resolved"),
        ]
        buckets: dict[str, list[dict[str, Any]]] = {k: [] for k, _ in column_order}
        links_by_src: dict[str, list[dict[str, Any]]] = {}
        links_by_tgt: dict[str, list[dict[str, Any]]] = {}
        for lnk in env.links:
            links_by_src.setdefault(lnk["source_id"], []).append(lnk)
            links_by_tgt.setdefault(lnk["target_id"], []).append(lnk)

        for rec in env.records:
            status = rec["status"] if rec["status"] in buckets else "active"
            track = (rec.get("facets", {}).get("track") or ["general"])[0]
            buckets[status].append(
                {
                    "record_id": rec["record_id"],
                    "track": track,
                    "kind": rec["kind"],
                    "title": rec["title"],
                    "owner": rec["owner"],
                    "status": rec["status"],
                    "summary": rec["summary"],
                    "superseded_by": rec["superseded_by"],
                    "open_stale_alerts": rec["open_stale_alerts"],
                    "outgoing": [
                        {"relation": l["relation"], "target_id": l["target_id"]}
                        for l in links_by_src.get(rec["record_id"], [])
                    ],
                    "incoming": [
                        {"relation": l["relation"], "source_id": l["source_id"]}
                        for l in links_by_tgt.get(rec["record_id"], [])
                    ],
                }
            )

        columns = [
            {"id": col_id, "label": label, "count": len(buckets[col_id]), "cards": buckets[col_id]}
            for col_id, label in column_order
            if buckets[col_id] or col_id in ("blocked", "pending_signoff", "superseded")
        ]
        return {
            "layout": "kanban_dependency_cards",
            "total_cards": env.record_count,
            "total_edges": len(env.links),
            "open_alerts": len(env.freshness_alerts),
            "columns": columns,
        }

    def _export_mdx_document(
        self,
        manifest: ArtifactManifest,
        port_name: str,
        env: CollectionEnvelopeV1,
    ) -> str:
        """Generate a valid Native `Document kind:artifact` (`native.mdx.artifact.v2`) payload."""
        inputs_yaml = "\n".join(
            [
                f"  - name: {b.name}\n"
                f"    envelope: {b.envelope}\n"
                f"    collection: {b.collection}\n"
                f"    required: {'true' if b.required else 'false'}\n"
                f"    expose_to_root: {'true' if b.expose_to_root else 'false'}"
                for b in manifest.inputs
            ]
        )
        caps_yaml = "\n".join(f"  - {c}" for c in manifest.capability_requests)
        return (
            "---\n"
            "kind: artifact\n"
            f"id: {manifest.artifact_id}\n"
            f"schema: {manifest.schema_version}\n"
            f"title: {json.dumps(manifest.title)}\n"
            "inputs:\n"
            f"{inputs_yaml}\n"
            "capability_requests:\n"
            f"{caps_yaml}\n"
            "---\n\n"
            f"export const meta = {{ caller: {json.dumps(env.caller_id)}, records: {env.record_count} }};\n\n"
            f"# {manifest.title}\n\n"
            "<NativeCollectionTable\n"
            f"  envelope={{inputs.{port_name}}}\n"
            '  columns={["record_id", "kind", "status", "owner", "open_stale_alerts", "superseded_by"]}\n'
            '  highlightStale={true}\n'
            '  onSelectRecord={(id) => host.navigateRecord({ recordId: id, gesture: "user_click" })}\n'
            "/>\n"
        )

    def _export_html_document(
        self,
        manifest: ArtifactManifest,
        port_name: str,
        env: CollectionEnvelopeV1,
        view_model: dict[str, Any],
    ) -> str:
        """Generate a valid Native `Document kind:artifact` (`native.html.artifact.v2`) payload."""
        contract_meta = {
            "kind": "artifact",
            "id": manifest.artifact_id,
            "schema": manifest.schema_version,
            "inputs": [b.model_dump() for b in manifest.inputs],
            "capability_requests": manifest.capability_requests,
        }
        cols_html = []
        for col in view_model["columns"]:
            cards_html = []
            for card in col["cards"]:
                stale_badge = (
                    f'<span class="badge stale">STALE ({card["open_stale_alerts"]})</span>'
                    if card["open_stale_alerts"] > 0
                    else ""
                )
                cards_html.append(
                    f'<article class="card" data-record="{html.escape(card["record_id"])}">'
                    f'<header><strong>{html.escape(card["title"])}</strong>{stale_badge}</header>'
                    f'<p>{html.escape(card["summary"])}</p>'
                    f'<footer><span>{html.escape(card["owner"])}</span><code>{html.escape(card["record_id"])}</code></footer>'
                    "</article>"
                )
            cols_html.append(
                f'<section class="col"><h3>{html.escape(col["label"])} ({col["count"]})</h3>'
                + "".join(cards_html)
                + "</section>"
            )
        return (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '  <meta charset="utf-8" />\n'
            f"  <title>{html.escape(manifest.title)}</title>\n"
            f'  <script type="application/vnd.native.artifact+json">{json.dumps(contract_meta)}</script>\n'
            "  <style>body{font-family:system-ui,sans-serif;background:#0b0d10;color:#e5e7eb;margin:0;padding:16px}"
            ".board{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}"
            ".col{background:#12161c;border:1px solid #222933;border-radius:10px;padding:12px}"
            ".card{background:#181e26;border:1px solid #2b3441;border-radius:8px;padding:10px;margin-bottom:8px}"
            ".badge.stale{background:#78350f;color:#fde68a;font-size:11px;padding:2px 6px;border-radius:99px;margin-left:6px}</style>\n"
            "</head>\n"
            f'<body data-port="{html.escape(port_name)}" data-caller="{html.escape(env.caller_id)}">\n'
            f'  <main class="board">{"".join(cols_html)}</main>\n'
            "</body>\n"
            "</html>\n"
        )
