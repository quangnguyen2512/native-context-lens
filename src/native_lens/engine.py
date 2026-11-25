"""Governed Event-Sourced SQLite WAL Context Engine.

Architectural invariant (mirroring withnative/native):
  operation contract -> caller identity + authorization (fail-closed)
  -> governed domain operations
  -> BEGIN IMMEDIATE: append authoritative event + deterministic projection
  -> records + links + facets + permissions + freshness_alerts

Projection tables are strictly derived and can be dropped & replayed bit-for-bit
from the append-only `events` table via `rebuild_projections()`.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from native_lens.models import (
    BlockerChainResult,
    BlockerHop,
    CallerContext,
    EventEntry,
    FreshnessAlert,
    LinkModel,
    RecordModel,
    ReplayVerification,
)


class AuthorizationError(PermissionError):
    """Raised when a caller fails a governed read or write authorization check."""


class RecordNotFoundError(LookupError):
    """Raised when a target record does not exist or is invisible to the caller."""


DEFAULT_PERSONAS: dict[str, CallerContext] = {
    "founder": CallerContext(
        caller_id="george",
        display_name="George (Founder)",
        roles=["founder", "member"],
    ),
    "engineer": CallerContext(
        caller_id="devon",
        display_name="Devon (Core Engineer)",
        roles=["member"],
    ),
    "contractor": CallerContext(
        caller_id="alex_ext",
        display_name="Alex (External Contractor)",
        roles=["contractor"],
    ),
    "anonymous": CallerContext(
        caller_id="anon_guest",
        display_name="Unauthenticated Guest",
        roles=[],
    ),
}

VALID_RELATIONS = frozenset({"blocks", "supersedes", "depends_on", "references", "waiting_on"})
WRITE_ROLES = frozenset({"founder", "member"})
GENESIS_HASH = "0" * 64


def estimate_tokens(text: str) -> int:
    """Deterministic word-piece token estimator (~4 chars/token, calibrated for English/JSON)."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _compute_event_hash(
    prev_hash: str,
    event_type: str,
    aggregate_id: str,
    actor_id: str,
    payload_json: str,
    created_at: str,
) -> str:
    raw = "|".join([prev_hash, event_type, aggregate_id, actor_id, payload_json, created_at])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class NativeContextEngine:
    """Event-sourced SQLite WAL engine with atomic projection, ACLs & stale propagation."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self._configure_connection()
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _configure_connection(self) -> None:
        if self.db_path != ":memory:":
            self.conn.execute("PRAGMA journal_mode = WAL;")
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.conn.execute("PRAGMA synchronous = NORMAL;")
        self.conn.execute("PRAGMA busy_timeout = 5000;")

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_aggregate ON events(aggregate_id);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
            """
        )
        self._create_projection_tables()

    def _create_projection_tables(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS records (
                record_id TEXT PRIMARY KEY,
                collection TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL,
                owner TEXT NOT NULL,
                summary TEXT NOT NULL,
                body TEXT NOT NULL,
                superseded_by TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL,
                source_path TEXT
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_records_collection ON records(collection)",
            "CREATE INDEX IF NOT EXISTS idx_records_status ON records(status)",
            """
            CREATE TABLE IF NOT EXISTS links (
                link_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(source_id, target_id, relation)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_links_source ON links(source_id, relation)",
            "CREATE INDEX IF NOT EXISTS idx_links_target ON links(target_id, relation)",
            """
            CREATE TABLE IF NOT EXISTS facets (
                record_id TEXT NOT NULL,
                facet_key TEXT NOT NULL,
                facet_value TEXT NOT NULL,
                PRIMARY KEY (record_id, facet_key, facet_value)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_facets_kv ON facets(facet_key, facet_value)",
            """
            CREATE TABLE IF NOT EXISTS permissions (
                scope_type TEXT NOT NULL CHECK(scope_type IN ('record', 'collection')),
                scope_id TEXT NOT NULL,
                principal TEXT NOT NULL,
                effect TEXT NOT NULL CHECK(effect IN ('allow', 'deny')),
                PRIMARY KEY (scope_type, scope_id, principal)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_permissions_principal ON permissions(principal, scope_type)",
            """
            CREATE TABLE IF NOT EXISTS freshness_alerts (
                alert_id TEXT PRIMARY KEY,
                affected_record_id TEXT NOT NULL,
                trigger_record_id TEXT NOT NULL,
                replacement_record_id TEXT,
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                hops INTEGER NOT NULL,
                path_json TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_alerts_affected ON freshness_alerts(affected_record_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_alerts_trigger ON freshness_alerts(trigger_record_id)",
        ]
        for stmt in statements:
            self.conn.execute(stmt)

    # ------------------------------------------------------------------
    # Authorization Helpers (Fail-Closed)
    # ------------------------------------------------------------------

    def resolve_caller(self, caller: CallerContext | str) -> CallerContext:
        if isinstance(caller, CallerContext):
            return caller
        if caller in DEFAULT_PERSONAS:
            return DEFAULT_PERSONAS[caller]
        for persona in DEFAULT_PERSONAS.values():
            if persona.caller_id == caller:
                return persona
        return CallerContext(caller_id=caller, display_name=caller, roles=[])

    def _require_write_access(self, caller: CallerContext, require_founder: bool = False) -> None:
        if require_founder:
            if "founder" not in caller.roles:
                raise AuthorizationError(
                    f"Caller '{caller.caller_id}' lacks 'founder' role required for this operation."
                )
            return
        if not (set(caller.roles) & WRITE_ROLES):
            raise AuthorizationError(
                f"Caller '{caller.caller_id}' (roles={caller.roles}) is not authorized to mutate context."
            )

    def _authorized_records_cte(self, principals: list[str]) -> tuple[str, list[str]]:
        """Build a strictly parameterized, fail-closed SQL CTE for readable records.

        Rule:
        - If `principals` is empty, returns zero rows (fail-closed).
        - Explicit `deny` on either the record or its collection ALWAYS blocks access.
        - If the record has any record-level `allow` entry, the caller MUST match a
          record-level `allow` (record ACL overrides broader collection allow!).
        - Otherwise, the caller must match a collection-level `allow`.
        """
        if not principals:
            return "authorized_records AS (SELECT record_id FROM records WHERE 1 = 0)", []
        placeholders = ", ".join("?" for _ in principals)
        cte = f"""
        authorized_records AS (
            SELECT r.record_id
            FROM records r
            WHERE (
                EXISTS (
                    SELECT 1 FROM permissions p
                    WHERE p.scope_type = 'record'
                      AND p.scope_id = r.record_id
                      AND p.effect = 'allow'
                      AND p.principal IN ({placeholders})
                )
                OR (
                    NOT EXISTS (
                        SELECT 1 FROM permissions p_rec
                        WHERE p_rec.scope_type = 'record'
                          AND p_rec.scope_id = r.record_id
                          AND p_rec.effect = 'allow'
                    )
                    AND EXISTS (
                        SELECT 1 FROM permissions p_col
                        WHERE p_col.scope_type = 'collection'
                          AND p_col.scope_id = r.collection
                          AND p_col.effect = 'allow'
                          AND p_col.principal IN ({placeholders})
                    )
                )
            )
            AND NOT EXISTS (
                SELECT 1 FROM permissions p_deny
                WHERE p_deny.effect = 'deny'
                  AND p_deny.principal IN ({placeholders})
                  AND (
                      (p_deny.scope_type = 'record' AND p_deny.scope_id = r.record_id)
                      OR (p_deny.scope_type = 'collection' AND p_deny.scope_id = r.collection)
                  )
            )
        )
        """
        return cte, principals + principals + principals

    def can_access_collection(self, collection: str, caller: CallerContext | str) -> bool:
        """Fail-closed check whether caller has explicit collection allow and no collection deny."""
        ctx = self.resolve_caller(caller)
        principals = ctx.principals
        if not principals:
            return False
        placeholders = ", ".join("?" for _ in principals)
        denied = self.conn.execute(
            f"""
            SELECT 1 FROM permissions
            WHERE scope_type = 'collection' AND scope_id = ?
              AND effect = 'deny' AND principal IN ({placeholders})
            LIMIT 1
            """,
            [collection, *principals],
        ).fetchone()
        if denied:
            return False
        allowed = self.conn.execute(
            f"""
            SELECT 1 FROM permissions
            WHERE scope_type = 'collection' AND scope_id = ?
              AND effect = 'allow' AND principal IN ({placeholders})
            LIMIT 1
            """,
            [collection, *principals],
        ).fetchone()
        return allowed is not None

    # ------------------------------------------------------------------
    # Atomic Event Append + Deterministic Projection
    # ------------------------------------------------------------------

    def _append_and_project(
        self,
        event_type: str,
        aggregate_id: str,
        actor_id: str,
        payload: dict[str, Any],
        created_at: str | None = None,
        event_id: str | None = None,
    ) -> EventEntry:
        """Atomically append to authoritative `events` AND project inside BEGIN IMMEDIATE."""
        ts = created_at or _utc_now_iso()
        eid = event_id or f"evt_{uuid.uuid4().hex[:12]}"
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))

        self.conn.execute("BEGIN IMMEDIATE;")
        try:
            row = self.conn.execute(
                "SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            prev_hash = row["event_hash"] if row else GENESIS_HASH
            event_hash = _compute_event_hash(
                prev_hash, event_type, aggregate_id, actor_id, payload_json, ts
            )
            cur = self.conn.execute(
                """
                INSERT INTO events (
                    event_id, event_type, aggregate_id, actor_id,
                    payload_json, created_at, prev_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (eid, event_type, aggregate_id, actor_id, payload_json, ts, prev_hash, event_hash),
            )
            seq = int(cur.lastrowid)
            self._project_event(eid, event_type, aggregate_id, payload, ts)
            self.conn.execute("COMMIT;")
            return EventEntry(
                seq=seq,
                event_id=eid,
                event_type=event_type,
                aggregate_id=aggregate_id,
                actor_id=actor_id,
                payload=payload,
                created_at=ts,
                prev_hash=prev_hash,
                event_hash=event_hash,
            )
        except Exception:
            self.conn.execute("ROLLBACK;")
            raise

    def _project_event(
        self,
        event_id: str,
        event_type: str,
        aggregate_id: str,
        payload: dict[str, Any],
        created_at: str,
    ) -> None:
        """Pure deterministic projector: uses ONLY event fields + existing projection tables."""
        if event_type == "RECORD_CREATED":
            self.conn.execute(
                """
                INSERT OR REPLACE INTO records (
                    record_id, collection, kind, title, status, owner,
                    summary, body, superseded_by, version, updated_at, source_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    aggregate_id,
                    payload["collection"],
                    payload["kind"],
                    payload["title"],
                    payload["status"],
                    payload["owner"],
                    payload["summary"],
                    payload.get("body", ""),
                    payload.get("superseded_by"),
                    created_at,
                    payload.get("source_path"),
                ),
            )
            self.conn.execute("DELETE FROM facets WHERE record_id = ?", (aggregate_id,))
            for key, values in sorted(payload.get("facets", {}).items()):
                vals = values if isinstance(values, list) else [values]
                for val in sorted({str(v) for v in vals}):
                    self.conn.execute(
                        "INSERT OR IGNORE INTO facets (record_id, facet_key, facet_value) VALUES (?, ?, ?)",
                        (aggregate_id, str(key), val),
                    )

        elif event_type == "RECORD_UPDATED":
            existing = self.conn.execute(
                "SELECT * FROM records WHERE record_id = ?", (aggregate_id,)
            ).fetchone()
            if not existing:
                raise RecordNotFoundError(f"Cannot project update for missing record '{aggregate_id}'.")
            self.conn.execute(
                """
                UPDATE records
                SET title = ?, status = ?, owner = ?, summary = ?, body = ?,
                    superseded_by = ?, version = version + 1, updated_at = ?
                WHERE record_id = ?
                """,
                (
                    payload.get("title", existing["title"]),
                    payload.get("status", existing["status"]),
                    payload.get("owner", existing["owner"]),
                    payload.get("summary", existing["summary"]),
                    payload.get("body", existing["body"]),
                    payload.get("superseded_by", existing["superseded_by"]),
                    created_at,
                    aggregate_id,
                ),
            )
            if "facets" in payload and payload["facets"] is not None:
                self.conn.execute("DELETE FROM facets WHERE record_id = ?", (aggregate_id,))
                for key, values in sorted(payload["facets"].items()):
                    vals = values if isinstance(values, list) else [values]
                    for val in sorted({str(v) for v in vals}):
                        self.conn.execute(
                            "INSERT OR IGNORE INTO facets (record_id, facet_key, facet_value) VALUES (?, ?, ?)",
                            (aggregate_id, str(key), val),
                        )
            if payload.get("propagate_stale", True):
                self._propagate_stale_context(
                    trigger_record_id=aggregate_id,
                    replacement_record_id=None,
                    alert_type="STALE_DEPENDENCY",
                    reason=payload.get("change_note", f"Upstream record '{aggregate_id}' was updated."),
                    created_at=created_at,
                )

        elif event_type == "LINK_ADDED":
            link_id = payload["link_id"]
            source_id = payload["source_id"]
            target_id = payload["target_id"]
            relation = payload["relation"]
            note = payload.get("note", "")
            self.conn.execute(
                """
                INSERT OR REPLACE INTO links (link_id, source_id, target_id, relation, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (link_id, source_id, target_id, relation, note, created_at),
            )
            if relation == "supersedes":
                self._apply_supersession(
                    old_record_id=target_id,
                    new_record_id=source_id,
                    reason=note or f"Superseded by {source_id}",
                    created_at=created_at,
                )

        elif event_type == "LINK_REMOVED":
            self.conn.execute(
                "DELETE FROM links WHERE source_id = ? AND target_id = ? AND relation = ?",
                (payload["source_id"], payload["target_id"], payload["relation"]),
            )

        elif event_type == "RECORD_SUPERSEDED":
            old_id = aggregate_id
            new_id = payload["superseded_by"]
            reason = payload.get("reason", f"Superseded by {new_id}")
            link_id = payload.get("link_id", f"lnk:{new_id}:supersedes:{old_id}")
            self.conn.execute(
                """
                INSERT OR REPLACE INTO links (link_id, source_id, target_id, relation, note, created_at)
                VALUES (?, ?, ?, 'supersedes', ?, ?)
                """,
                (link_id, new_id, old_id, reason, created_at),
            )
            self._apply_supersession(
                old_record_id=old_id,
                new_record_id=new_id,
                reason=reason,
                created_at=created_at,
            )

        elif event_type == "ACL_GRANTED":
            self.conn.execute(
                """
                INSERT OR REPLACE INTO permissions (scope_type, scope_id, principal, effect)
                VALUES (?, ?, ?, ?)
                """,
                (
                    payload["scope_type"],
                    payload["scope_id"],
                    payload["principal"],
                    payload["effect"],
                ),
            )

        elif event_type == "ACL_REVOKED":
            self.conn.execute(
                """
                DELETE FROM permissions
                WHERE scope_type = ? AND scope_id = ? AND principal = ?
                """,
                (payload["scope_type"], payload["scope_id"], payload["principal"]),
            )

        elif event_type == "ALERT_RESOLVED":
            self.conn.execute(
                "UPDATE freshness_alerts SET status = 'resolved' WHERE alert_id = ?",
                (aggregate_id,),
            )

        else:
            raise ValueError(f"Unknown event_type '{event_type}'")

    def _apply_supersession(
        self,
        old_record_id: str,
        new_record_id: str,
        reason: str,
        created_at: str,
    ) -> None:
        self.conn.execute(
            """
            UPDATE records
            SET status = 'superseded', superseded_by = ?, version = version + 1, updated_at = ?
            WHERE record_id = ?
            """,
            (new_record_id, created_at, old_record_id),
        )
        self._propagate_stale_context(
            trigger_record_id=old_record_id,
            replacement_record_id=new_record_id,
            alert_type="STALE_DEPENDENCY",
            reason=reason,
            created_at=created_at,
        )

    def _propagate_stale_context(
        self,
        trigger_record_id: str,
        replacement_record_id: str | None,
        alert_type: str,
        reason: str,
        created_at: str,
    ) -> None:
        """Traverse all downstream dependents via a recursive SQL CTE and emit alerts atomically."""
        rows = self.conn.execute(
            """
            WITH RECURSIVE downstream(record_id, hops, path_str) AS (
                -- Direct dependents: X depends_on/references/waiting_on trigger, OR trigger blocks X
                SELECT DISTINCT
                    CASE
                        WHEN l.relation IN ('depends_on', 'references', 'waiting_on') THEN l.source_id
                        WHEN l.relation = 'blocks' THEN l.target_id
                    END AS record_id,
                    1 AS hops,
                    '|' || ? || '|' ||
                    CASE
                        WHEN l.relation IN ('depends_on', 'references', 'waiting_on') THEN l.source_id
                        WHEN l.relation = 'blocks' THEN l.target_id
                    END || '|' AS path_str
                FROM links l
                WHERE (
                    (l.target_id = ? AND l.relation IN ('depends_on', 'references', 'waiting_on'))
                    OR (l.source_id = ? AND l.relation = 'blocks')
                )

                UNION ALL

                SELECT
                    CASE
                        WHEN l.relation IN ('depends_on', 'references', 'waiting_on') THEN l.source_id
                        WHEN l.relation = 'blocks' THEN l.target_id
                    END AS record_id,
                    d.hops + 1 AS hops,
                    d.path_str ||
                    CASE
                        WHEN l.relation IN ('depends_on', 'references', 'waiting_on') THEN l.source_id
                        WHEN l.relation = 'blocks' THEN l.target_id
                    END || '|' AS path_str
                FROM downstream d
                JOIN links l ON (
                    (l.target_id = d.record_id AND l.relation IN ('depends_on', 'references', 'waiting_on'))
                    OR (l.source_id = d.record_id AND l.relation = 'blocks')
                )
                WHERE d.hops < 10
                  AND instr(
                      d.path_str,
                      '|' || CASE
                          WHEN l.relation IN ('depends_on', 'references', 'waiting_on') THEN l.source_id
                          WHEN l.relation = 'blocks' THEN l.target_id
                      END || '|'
                  ) = 0
            )
            SELECT
                d.record_id AS affected_record_id,
                MIN(d.hops) AS min_hops,
                MIN(d.path_str) AS path_str,
                r.kind AS affected_kind,
                r.title AS affected_title
            FROM downstream d
            JOIN records r ON r.record_id = d.record_id
            WHERE d.record_id != ?
              AND (? IS NULL OR d.record_id != ?)
            GROUP BY d.record_id, r.kind, r.title
            ORDER BY min_hops ASC, d.record_id ASC
            """,
            (
                trigger_record_id,
                trigger_record_id,
                trigger_record_id,
                trigger_record_id,
                replacement_record_id,
                replacement_record_id,
            ),
        ).fetchall()

        for row in rows:
            affected_id = row["affected_record_id"]
            hops = int(row["min_hops"])
            path_nodes = [p for p in row["path_str"].split("|") if p]
            severity = (
                "critical"
                if (hops == 1 or row["affected_kind"] in ("deal", "freeze", "audit"))
                else "high"
            )
            alert_id = (
                f"stale:{trigger_record_id}:{replacement_record_id or 'upd'}:{affected_id}"
            )
            if replacement_record_id:
                msg = (
                    f"'{row['affected_title']}' relies on superseded '{trigger_record_id}' "
                    f"({hops} hop{'s' if hops != 1 else ''}); re-anchor to '{replacement_record_id}'. {reason}"
                )
            else:
                msg = (
                    f"'{row['affected_title']}' depends on updated '{trigger_record_id}' "
                    f"({hops} hop{'s' if hops != 1 else ''}). {reason}"
                )
            self.conn.execute(
                """
                INSERT OR REPLACE INTO freshness_alerts (
                    alert_id, affected_record_id, trigger_record_id, replacement_record_id,
                    alert_type, severity, hops, path_json, message, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
                """,
                (
                    alert_id,
                    affected_id,
                    trigger_record_id,
                    replacement_record_id,
                    alert_type,
                    severity,
                    hops,
                    json.dumps(path_nodes),
                    msg.strip(),
                    created_at,
                ),
            )

    # ------------------------------------------------------------------
    # Governed Domain Write Operations
    # ------------------------------------------------------------------

    def grant_acl(
        self,
        scope_type: str,
        scope_id: str,
        principal: str,
        effect: str = "allow",
        caller: CallerContext | str = "founder",
    ) -> EventEntry:
        ctx = self.resolve_caller(caller)
        self._require_write_access(ctx, require_founder=True)
        if scope_type not in ("record", "collection"):
            raise ValueError(f"Invalid scope_type '{scope_type}'")
        if effect not in ("allow", "deny"):
            raise ValueError(f"Invalid effect '{effect}'")
        return self._append_and_project(
            event_type="ACL_GRANTED",
            aggregate_id=f"{scope_type}:{scope_id}",
            actor_id=ctx.caller_id,
            payload={
                "scope_type": scope_type,
                "scope_id": scope_id,
                "principal": principal,
                "effect": effect,
            },
        )

    def create_record(
        self,
        *,
        record_id: str,
        collection: str,
        kind: str,
        title: str,
        status: str,
        owner: str,
        summary: str,
        body: str = "",
        facets: dict[str, list[str]] | None = None,
        source_path: str | None = None,
        caller: CallerContext | str = "founder",
        created_at: str | None = None,
    ) -> EventEntry:
        ctx = self.resolve_caller(caller)
        self._require_write_access(ctx)
        return self._append_and_project(
            event_type="RECORD_CREATED",
            aggregate_id=record_id,
            actor_id=ctx.caller_id,
            payload={
                "collection": collection,
                "kind": kind,
                "title": title,
                "status": status,
                "owner": owner,
                "summary": summary,
                "body": body,
                "facets": facets or {},
                "source_path": source_path,
            },
            created_at=created_at,
        )

    def update_record(
        self,
        record_id: str,
        *,
        title: str | None = None,
        status: str | None = None,
        owner: str | None = None,
        summary: str | None = None,
        body: str | None = None,
        facets: dict[str, list[str]] | None = None,
        change_note: str = "",
        propagate_stale: bool = True,
        caller: CallerContext | str = "founder",
    ) -> EventEntry:
        ctx = self.resolve_caller(caller)
        self._require_write_access(ctx)
        # Verify record exists AND caller can read it (fail-closed write check)
        _ = self.get_record(record_id, caller=ctx)
        payload: dict[str, Any] = {
            "change_note": change_note,
            "propagate_stale": propagate_stale,
        }
        if title is not None:
            payload["title"] = title
        if status is not None:
            payload["status"] = status
        if owner is not None:
            payload["owner"] = owner
        if summary is not None:
            payload["summary"] = summary
        if body is not None:
            payload["body"] = body
        if facets is not None:
            payload["facets"] = facets
        return self._append_and_project(
            event_type="RECORD_UPDATED",
            aggregate_id=record_id,
            actor_id=ctx.caller_id,
            payload=payload,
        )

    def add_link(
        self,
        *,
        source_id: str,
        target_id: str,
        relation: str,
        note: str = "",
        caller: CallerContext | str = "founder",
        created_at: str | None = None,
    ) -> EventEntry:
        ctx = self.resolve_caller(caller)
        self._require_write_access(ctx)
        if relation not in VALID_RELATIONS:
            raise ValueError(f"Unsupported relation '{relation}'. Must be in {sorted(VALID_RELATIONS)}")
        link_id = f"lnk:{source_id}:{relation}:{target_id}"
        return self._append_and_project(
            event_type="LINK_ADDED",
            aggregate_id=link_id,
            actor_id=ctx.caller_id,
            payload={
                "link_id": link_id,
                "source_id": source_id,
                "target_id": target_id,
                "relation": relation,
                "note": note,
            },
            created_at=created_at,
        )

    def supersede_record(
        self,
        *,
        old_record_id: str,
        new_record_id: str,
        reason: str = "",
        caller: CallerContext | str = "founder",
        created_at: str | None = None,
    ) -> EventEntry:
        ctx = self.resolve_caller(caller)
        self._require_write_access(ctx)
        # Ensure caller can see both records before superseding
        _ = self.get_record(old_record_id, caller=ctx)
        _ = self.get_record(new_record_id, caller=ctx)
        return self._append_and_project(
            event_type="RECORD_SUPERSEDED",
            aggregate_id=old_record_id,
            actor_id=ctx.caller_id,
            payload={
                "superseded_by": new_record_id,
                "reason": reason or f"Superseded by {new_record_id}",
                "link_id": f"lnk:{new_record_id}:supersedes:{old_record_id}",
            },
            created_at=created_at,
        )

    # ------------------------------------------------------------------
    # Governed Read Operations (Fail-Closed SQL CTEs)
    # ------------------------------------------------------------------

    def get_record(self, record_id: str, caller: CallerContext | str = "founder") -> RecordModel:
        ctx = self.resolve_caller(caller)
        cte, cte_params = self._authorized_records_cte(ctx.principals)
        row = self.conn.execute(
            f"""
            WITH {cte}
            SELECT r.*,
                   (SELECT COUNT(*) FROM freshness_alerts fa
                    WHERE fa.affected_record_id = r.record_id AND fa.status = 'open') AS open_stale_alerts
            FROM records r
            JOIN authorized_records ar ON ar.record_id = r.record_id
            WHERE r.record_id = ?
            """,
            [*cte_params, record_id],
        ).fetchone()
        if not row:
            raise RecordNotFoundError(
                f"Record '{record_id}' not found or caller '{ctx.caller_id}' lacks access."
            )
        return self._row_to_record(row)

    def query_records(
        self,
        *,
        caller: CallerContext | str = "founder",
        collection: str | None = None,
        status: str | None = None,
        kind: str | None = None,
    ) -> list[RecordModel]:
        ctx = self.resolve_caller(caller)
        cte, cte_params = self._authorized_records_cte(ctx.principals)
        clauses = ["1 = 1"]
        params: list[Any] = list(cte_params)
        if collection:
            clauses.append("r.collection = ?")
            params.append(collection)
        if status:
            clauses.append("r.status = ?")
            params.append(status)
        if kind:
            clauses.append("r.kind = ?")
            params.append(kind)

        rows = self.conn.execute(
            f"""
            WITH {cte}
            SELECT r.*,
                   (SELECT COUNT(*) FROM freshness_alerts fa
                    WHERE fa.affected_record_id = r.record_id AND fa.status = 'open') AS open_stale_alerts
            FROM records r
            JOIN authorized_records ar ON ar.record_id = r.record_id
            WHERE {' AND '.join(clauses)}
            ORDER BY r.collection ASC, r.record_id ASC
            """,
            params,
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def list_links(
        self,
        *,
        caller: CallerContext | str = "founder",
        record_ids: list[str] | None = None,
    ) -> list[LinkModel]:
        """Return only links where BOTH endpoints are authorized for the caller (zero leakage)."""
        ctx = self.resolve_caller(caller)
        cte, cte_params = self._authorized_records_cte(ctx.principals)
        params: list[Any] = list(cte_params)
        extra = ""
        if record_ids:
            ph = ", ".join("?" for _ in record_ids)
            extra = f" AND (l.source_id IN ({ph}) OR l.target_id IN ({ph}))"
            params.extend(record_ids)
            params.extend(record_ids)

        rows = self.conn.execute(
            f"""
            WITH {cte}
            SELECT l.*
            FROM links l
            JOIN authorized_records a_src ON a_src.record_id = l.source_id
            JOIN authorized_records a_tgt ON a_tgt.record_id = l.target_id
            WHERE 1 = 1 {extra}
            ORDER BY l.source_id ASC, l.relation ASC, l.target_id ASC
            """,
            params,
        ).fetchall()
        return [
            LinkModel(
                link_id=r["link_id"],
                source_id=r["source_id"],
                target_id=r["target_id"],
                relation=r["relation"],
                note=r["note"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def list_freshness_alerts(
        self,
        *,
        caller: CallerContext | str = "founder",
        status: str | None = "open",
        collection: str | None = None,
    ) -> list[FreshnessAlert]:
        """List freshness alerts filtered fail-closed so unauthorized records never leak."""
        ctx = self.resolve_caller(caller)
        cte, cte_params = self._authorized_records_cte(ctx.principals)
        clauses = ["1 = 1"]
        params: list[Any] = list(cte_params)
        if status:
            clauses.append("fa.status = ?")
            params.append(status)
        if collection:
            clauses.append("r_aff.collection = ?")
            params.append(collection)

        rows = self.conn.execute(
            f"""
            WITH {cte}
            SELECT
                fa.*,
                r_aff.title AS affected_title,
                r_trg.title AS trigger_title,
                r_rep.title AS replacement_title
            FROM freshness_alerts fa
            JOIN authorized_records ar_aff ON ar_aff.record_id = fa.affected_record_id
            JOIN authorized_records ar_trg ON ar_trg.record_id = fa.trigger_record_id
            JOIN records r_aff ON r_aff.record_id = fa.affected_record_id
            JOIN records r_trg ON r_trg.record_id = fa.trigger_record_id
            LEFT JOIN authorized_records ar_rep ON ar_rep.record_id = fa.replacement_record_id
            LEFT JOIN records r_rep ON r_rep.record_id = ar_rep.record_id
            WHERE (fa.replacement_record_id IS NULL OR ar_rep.record_id IS NOT NULL)
              AND {' AND '.join(clauses)}
            ORDER BY fa.hops ASC, fa.created_at DESC, fa.alert_id ASC
            """,
            params,
        ).fetchall()
        return [
            FreshnessAlert(
                alert_id=r["alert_id"],
                affected_record_id=r["affected_record_id"],
                affected_title=r["affected_title"],
                trigger_record_id=r["trigger_record_id"],
                trigger_title=r["trigger_title"],
                replacement_record_id=r["replacement_record_id"],
                replacement_title=r["replacement_title"],
                alert_type=r["alert_type"],
                severity=r["severity"],
                hops=int(r["hops"]),
                path=json.loads(r["path_json"]),
                message=r["message"],
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    def trace_blocker_chain(
        self,
        record_id: str,
        caller: CallerContext | str = "founder",
    ) -> BlockerChainResult:
        """Solve multi-hop decision & blocker chains in ONE governed recursive SQL CTE.

        Follows:
          1. outgoing `depends_on`, `waiting_on`, `references`
          2. incoming `blocks` (labelled `blocked_by`)
          3. incoming `supersedes` (labelled `superseded_by`)

        Enforces caller ACLs inside the exact same single SQL query (`authorized_records`).
        """
        ctx = self.resolve_caller(caller)
        cte, cte_params = self._authorized_records_cte(ctx.principals)
        t0 = time.perf_counter()

        rows = self.conn.execute(
            f"""
            WITH RECURSIVE
            {cte},
            blocker_chain(record_id, hop, via_relation, from_record_id, path_str) AS (
                SELECT
                    r.record_id,
                    0 AS hop,
                    'root' AS via_relation,
                    NULL AS from_record_id,
                    '|' || r.record_id || '|' AS path_str
                FROM records r
                JOIN authorized_records ar ON ar.record_id = r.record_id
                WHERE r.record_id = ?

                UNION ALL

                SELECT
                    nxt.next_id AS record_id,
                    bc.hop + 1 AS hop,
                    nxt.via_relation AS via_relation,
                    bc.record_id AS from_record_id,
                    bc.path_str || nxt.next_id || '|' AS path_str
                FROM blocker_chain bc
                JOIN (
                    SELECT source_id AS cur_id, target_id AS next_id, relation AS via_relation
                    FROM links
                    WHERE relation IN ('depends_on', 'waiting_on', 'references')
                    UNION ALL
                    SELECT target_id AS cur_id, source_id AS next_id, 'blocked_by' AS via_relation
                    FROM links
                    WHERE relation = 'blocks'
                    UNION ALL
                    SELECT target_id AS cur_id, source_id AS next_id, 'superseded_by' AS via_relation
                    FROM links
                    WHERE relation = 'supersedes'
                ) nxt ON nxt.cur_id = bc.record_id
                JOIN authorized_records ar_next ON ar_next.record_id = nxt.next_id
                WHERE bc.hop < 10
                  AND instr(bc.path_str, '|' || nxt.next_id || '|') = 0
            ),
            dedup AS (
                SELECT
                    record_id,
                    MIN(hop) AS hop
                FROM blocker_chain
                GROUP BY record_id
            )
            SELECT
                d.hop,
                r.record_id,
                r.title,
                r.kind,
                r.collection,
                r.status,
                r.owner,
                r.summary,
                r.superseded_by,
                (
                    SELECT bc2.via_relation FROM blocker_chain bc2
                    WHERE bc2.record_id = d.record_id AND bc2.hop = d.hop
                    ORDER BY bc2.via_relation ASC LIMIT 1
                ) AS via_relation,
                (
                    SELECT bc2.from_record_id FROM blocker_chain bc2
                    WHERE bc2.record_id = d.record_id AND bc2.hop = d.hop
                    ORDER BY bc2.via_relation ASC LIMIT 1
                ) AS from_record_id,
                (
                    SELECT COUNT(*) FROM freshness_alerts fa
                    WHERE fa.affected_record_id = r.record_id AND fa.status = 'open'
                ) AS open_stale_alerts
            FROM dedup d
            JOIN records r ON r.record_id = d.record_id
            ORDER BY d.hop ASC, r.record_id ASC
            """,
            [*cte_params, record_id],
        ).fetchall()

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)

        chain = [
            BlockerHop(
                hop=int(r["hop"]),
                record_id=r["record_id"],
                title=r["title"],
                kind=r["kind"],
                collection=r["collection"],
                status=r["status"],
                owner=r["owner"],
                summary=r["summary"],
                via_relation=r["via_relation"],
                from_record_id=r["from_record_id"],
                superseded_by=r["superseded_by"],
                open_stale_alerts=int(r["open_stale_alerts"]),
            )
            for r in rows
        ]

        # Terminal blockers: leaf nodes in the traversed chain (no outgoing traversed child)
        # excluding superseded historical records.
        parents_in_chain = {h.from_record_id for h in chain if h.from_record_id is not None}
        terminal_blockers = [
            h
            for h in chain
            if h.hop > 0 and h.record_id not in parents_in_chain and h.status != "superseded"
        ]
        if not terminal_blockers and chain:
            # Fallback to deepest non-superseded node
            non_sup = [h for h in chain if h.status != "superseded"]
            if non_sup:
                max_hop = max(h.hop for h in non_sup)
                terminal_blockers = [h for h in non_sup if h.hop == max_hop]

        superseded_nodes = [h.record_id for h in chain if h.status == "superseded"]

        # Compact structured MCP payload returned to an agent client:
        # carries exact graph hops + statuses without dumping raw document prose.
        compact_payload = {
            "root": record_id,
            "chain": [
                {
                    "hop": h.hop,
                    "id": h.record_id,
                    "via": h.via_relation,
                    "status": h.status,
                    "owner": h.owner,
                    **({"superseded_by": h.superseded_by} if h.superseded_by else {}),
                    **({"stale": h.open_stale_alerts} if h.open_stale_alerts else {}),
                }
                for h in chain
            ],
            "terminal_blockers": [
                {"id": h.record_id, "owner": h.owner, "summary": h.summary}
                for h in terminal_blockers
            ],
        }
        compact_json = json.dumps(compact_payload, separators=(",", ":"))

        return BlockerChainResult(
            root_record_id=record_id,
            caller_id=ctx.caller_id,
            sql_queries_executed=1,
            elapsed_ms=elapsed_ms,
            chain=chain,
            terminal_blockers=terminal_blockers,
            superseded_nodes=superseded_nodes,
            compact_payload_json=compact_json,
            estimated_tokens=estimate_tokens(compact_json),
        )

    # ------------------------------------------------------------------
    # Event Log Inspection & Deterministic Replay Verification
    # ------------------------------------------------------------------

    def list_events(self, limit: int = 100) -> list[EventEntry]:
        rows = self.conn.execute(
            "SELECT * FROM events ORDER BY seq DESC LIMIT ?", (limit,)
        ).fetchall()
        return [
            EventEntry(
                seq=int(r["seq"]),
                event_id=r["event_id"],
                event_type=r["event_type"],
                aggregate_id=r["aggregate_id"],
                actor_id=r["actor_id"],
                payload=json.loads(r["payload_json"]),
                created_at=r["created_at"],
                prev_hash=r["prev_hash"],
                event_hash=r["event_hash"],
            )
            for r in rows
        ]

    def verify_event_hash_chain(self) -> bool:
        rows = self.conn.execute("SELECT * FROM events ORDER BY seq ASC").fetchall()
        expected_prev = GENESIS_HASH
        for r in rows:
            if r["prev_hash"] != expected_prev:
                return False
            recomputed = _compute_event_hash(
                r["prev_hash"],
                r["event_type"],
                r["aggregate_id"],
                r["actor_id"],
                r["payload_json"],
                r["created_at"],
            )
            if recomputed != r["event_hash"]:
                return False
            expected_prev = r["event_hash"]
        return True

    def compute_projection_digest(self) -> str:
        """Deterministic SHA-256 hash across every derived projection table."""
        snapshot: dict[str, list[dict[str, Any]]] = {}
        queries = {
            "records": "SELECT * FROM records ORDER BY record_id ASC",
            "links": "SELECT * FROM links ORDER BY link_id ASC",
            "facets": "SELECT * FROM facets ORDER BY record_id ASC, facet_key ASC, facet_value ASC",
            "permissions": "SELECT * FROM permissions ORDER BY scope_type ASC, scope_id ASC, principal ASC",
            "freshness_alerts": "SELECT * FROM freshness_alerts ORDER BY alert_id ASC",
        }
        for table, sql in queries.items():
            rows = self.conn.execute(sql).fetchall()
            snapshot[table] = [dict(r) for r in rows]
        canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def rebuild_projections(self) -> ReplayVerification:
        """Drop ALL projection tables and deterministically replay from `events` alone."""
        before_digest = self.compute_projection_digest()
        chain_valid = self.verify_event_hash_chain()
        t0 = time.perf_counter()

        events = self.conn.execute("SELECT * FROM events ORDER BY seq ASC").fetchall()

        self.conn.execute("BEGIN IMMEDIATE;")
        try:
            for table in ("freshness_alerts", "permissions", "facets", "links", "records"):
                self.conn.execute(f"DROP TABLE IF EXISTS {table}")
            self._create_projection_tables()
            for ev in events:
                self._project_event(
                    event_id=ev["event_id"],
                    event_type=ev["event_type"],
                    aggregate_id=ev["aggregate_id"],
                    payload=json.loads(ev["payload_json"]),
                    created_at=ev["created_at"],
                )
            self.conn.execute("COMMIT;")
        except Exception:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK;")
            raise

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        after_digest = self.compute_projection_digest()

        return ReplayVerification(
            events_replayed=len(events),
            before_digest=before_digest,
            after_digest=after_digest,
            deterministic_match=(before_digest == after_digest),
            chain_integrity_valid=chain_valid,
            elapsed_ms=elapsed_ms,
        )

    def _row_to_record(self, row: sqlite3.Row) -> RecordModel:
        facet_rows = self.conn.execute(
            "SELECT facet_key, facet_value FROM facets WHERE record_id = ? ORDER BY facet_key, facet_value",
            (row["record_id"],),
        ).fetchall()
        facets: dict[str, list[str]] = {}
        for fr in facet_rows:
            facets.setdefault(fr["facet_key"], []).append(fr["facet_value"])
        return RecordModel(
            record_id=row["record_id"],
            collection=row["collection"],
            kind=row["kind"],
            title=row["title"],
            status=row["status"],
            owner=row["owner"],
            summary=row["summary"],
            body=row["body"],
            superseded_by=row["superseded_by"],
            version=int(row["version"]),
            updated_at=row["updated_at"],
            source_path=row["source_path"],
            facets=facets,
            open_stale_alerts=int(row["open_stale_alerts"]),
        )
