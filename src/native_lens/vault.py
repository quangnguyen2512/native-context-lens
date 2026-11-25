"""Markdown Vault parser & event-sourced ingester into NativeContextEngine."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from native_lens.engine import NativeContextEngine

WIKILINK_RE = re.compile(r"\[\[([a-zA-Z0-9_-]+)(?:\|[^\]]+)?\]\]")
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


@dataclass(frozen=True)
class ParsedVaultDoc:
    record_id: str
    path: Path
    raw_text: str
    meta: dict[str, Any]
    body: str
    wikilinks: list[str]


def parse_markdown_file(path: Path) -> ParsedVaultDoc:
    """Parse a Markdown file with lightweight YAML-subset frontmatter and [[wikilinks]]."""
    raw = path.read_text(encoding="utf-8")
    meta: dict[str, Any] = {}
    body = raw
    m = FRONTMATTER_RE.match(raw)
    if m:
        fm_block, body = m.group(1), m.group(2)
        meta = _parse_simple_frontmatter(fm_block)
    record_id = str(meta.get("id") or path.stem)
    wikilinks: list[str] = []
    for target in WIKILINK_RE.findall(body):
        if target not in wikilinks and target != record_id:
            wikilinks.append(target)
    return ParsedVaultDoc(
        record_id=record_id,
        path=path,
        raw_text=raw,
        meta=meta,
        body=body.strip(),
        wikilinks=wikilinks,
    )


def _parse_simple_frontmatter(block: str) -> dict[str, Any]:
    """Zero-dependency parser for structured YAML frontmatter (scalars, inline JSON lists/objects)."""
    data: dict[str, Any] = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, raw_val = stripped.split(":", 1)
        key = key.strip()
        val = raw_val.strip()
        if not val:
            data[key] = ""
        elif val.startswith("[") or val.startswith("{"):
            data[key] = json.loads(val)
        elif (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            data[key] = val[1:-1]
        elif val.lower() in ("true", "false"):
            data[key] = val.lower() == "true"
        else:
            data[key] = val
    return data


def default_vault_dir() -> Path:
    """Resolve the bundled 25-document company sample_vault directory."""
    return Path(__file__).resolve().parents[2] / "sample_vault"


def load_vault_documents(vault_dir: Path | None = None) -> list[ParsedVaultDoc]:
    root = vault_dir or default_vault_dir()
    files = sorted(root.glob("*.md"))
    return [parse_markdown_file(p) for p in files]


def load_vault_into_engine(
    engine: NativeContextEngine,
    vault_dir: Path | None = None,
) -> dict[str, int]:
    """Ingest a Markdown vault into NativeContextEngine via governed events.

    Order of ingestion:
      1. Collection-level baseline ACLs (`launch_blockers`, `reviews`, `decisions`, `signoffs`)
      2. All `RECORD_CREATED` events + record-level ACL overrides (`founder`-restricted docs)
      3. Non-superseding links (`depends_on`, `references`, `waiting_on`, `blocks`)
      4. `supersedes` links last so atomic stale-context propagation sees the full dependency graph!
    """
    docs = load_vault_documents(vault_dir)

    # 1. Baseline collection permissions (fail-closed: anonymous gets NOTHING)
    collections = sorted({str(d.meta.get("collection", "launch_blockers")) for d in docs})
    for col in collections:
        engine.grant_acl("collection", col, "role:founder", "allow", caller="founder")
        engine.grant_acl("collection", col, "role:member", "allow", caller="founder")
        engine.grant_acl("collection", col, "role:contractor", "allow", caller="founder")

    # 2. Records + record-level ACL restrictions
    for doc in docs:
        meta = doc.meta
        facets = meta.get("facets") if isinstance(meta.get("facets"), dict) else {}
        engine.create_record(
            record_id=doc.record_id,
            collection=str(meta.get("collection", "launch_blockers")),
            kind=str(meta.get("kind", "document")),
            title=str(meta.get("title", doc.record_id)),
            status=str(meta.get("status", "active")),
            owner=str(meta.get("owner", "Unassigned")),
            summary=str(meta.get("summary", "")),
            body=doc.body,
            facets=facets,
            source_path=doc.path.name,
            caller="founder",
            created_at=str(meta.get("updated_at", "2026-10-05T12:00:00Z")),
        )
        allowed_roles = meta.get("allowed_roles")
        if isinstance(allowed_roles, list) and allowed_roles:
            for role in allowed_roles:
                engine.grant_acl(
                    "record", doc.record_id, f"role:{role}", "allow", caller="founder"
                )

    # 3. Structural links (non-supersedes first)
    deferred_supersedes: list[tuple[str, str, str, str]] = []
    link_count = 0
    for doc in docs:
        links = doc.meta.get("links") or []
        ts = str(doc.meta.get("updated_at", "2026-10-05T12:00:00Z"))
        for entry in links:
            relation = entry["relation"]
            target = entry["target"]
            note = entry.get("note", "")
            if relation == "supersedes":
                deferred_supersedes.append((doc.record_id, target, note, ts))
            else:
                engine.add_link(
                    source_id=doc.record_id,
                    target_id=target,
                    relation=relation,
                    note=note,
                    caller="founder",
                    created_at=ts,
                )
                link_count += 1

    # 4. Supersedes links last -> triggers deterministic stale-context propagation
    for source_id, target_id, note, ts in deferred_supersedes:
        engine.add_link(
            source_id=source_id,
            target_id=target_id,
            relation="supersedes",
            note=note,
            caller="founder",
            created_at=ts,
        )
        link_count += 1

    return {
        "documents": len(docs),
        "links": link_count,
        "collections": len(collections),
    }
