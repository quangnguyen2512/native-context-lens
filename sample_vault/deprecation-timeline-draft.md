---
id: deprecation-timeline-draft
collection: launch_blockers
kind: decision
title: "API v1 Deprecation Timeline Draft (60-Day Raw HTTP Cutoff)"
status: active
owner: "Hannah Cho (DX Lead)"
updated_at: 2026-09-10T09:30:00Z
summary: "Initial September draft proposing an aggressive 60-day API v1 shutdown starting October 1."
facets: {"track": ["api_v1"], "quarter": ["Q3"], "priority": ["P2"]}
links: []
---

# API v1 Deprecation Timeline Draft (60-Day Raw HTTP Cutoff)

## Draft Schedule (Authored 2026-09-10)
To simplify the backend codebase ahead of GA, this draft proposed a fast 60-day deprecation window:
- **Oct 01:** Emit HTTP `Deprecation: true` header on all `/v1/*` routes.
- **Nov 01:** Disable creation of new v1 API keys; allow existing keys only.
- **Nov 30:** Hard HTTP `410 Gone` cutoff on all v1 routes.

## Migration Tooling Assumed
Under this draft, partners were expected to migrate directly against OpenAPI v2 REST specifications using raw `httpx` or `fetch` clients while SDK v3 remained in alpha.

## Risks Logged During Review
- Aggressive 60-day clock conflicts with enterprise change-freeze calendars in November.
- Lack of GA-grade SDK v3 packages risks breaking active pilot integrations (specifically Northwind's warehouse automation scripts) right before Q4 deal closing.
