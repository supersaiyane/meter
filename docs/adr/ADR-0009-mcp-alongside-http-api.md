# ADR-0009: An MCP server alongside the HTTP API, not instead of it

Date: 2026-08-23
Status: Accepted

## Context

The P0 specification defines an HTTP API in section 8. The question raised was
whether a Model Context Protocol server could replace it.

MCP is a JSON-RPC protocol for exposing typed tools and resources to a language
model client. It is an excellent fit for a conversational interface over
Meter's data, which is a requested feature.

## Decision

Build both. The HTTP API remains the single enforcement point. The MCP server
is a thin facade in front of it, in its own module `finops-mcp`.

```
React frontend  ----> HTTP API ----> service layer ----> repositories (scope guard)
                        ^
Claude, or any    ----> |
MCP client        MCP server
```

The MCP server calls the HTTP API over the network with the caller's token. It
does not reach into the service layer directly.

## Consequences

Positive.

- One enforcement point. Scope filtering, the audit log, rate limiting and the
  freshness envelope are implemented once and cannot be bypassed by adding a
  tool.
- MCP tools are typed and deterministic. The model composes them, it never
  computes a figure. That makes ADR-0007 mechanically enforced rather than a
  stated intention.
- The MCP server is the bot. FEAT-042 needs no separate backend.
- Any MCP client works, not only the bundled interface.

Negative.

- One extra network hop per tool call. Irrelevant at this scale, and the
  correctness gain is worth far more than the milliseconds.
- Two surfaces to keep in step. Mitigated by generating the MCP tool schemas
  from the same Pydantic models the API uses, so a drift is a build failure.

## Alternatives rejected

**MCP instead of the HTTP API.** Rejected on four counts.

1. A browser cannot speak MCP. The React frontend needs REST, and building a
   second protocol for it defeats the purpose.
2. MCP has no notion of a browser session, of pagination for a table, or of
   HTTP caching semantics. All three are needed by the interface.
3. Scope enforcement, the audit log and rate limiting would have to be
   reimplemented in the MCP layer. Two implementations of an authorization rule
   is how an authorization bug is created.
4. Operational tooling assumes HTTP. Load balancer health checks, access logs,
   tracing and WAF rules all work on the API and none work on stdio JSON-RPC.

**MCP server calling the service layer in process.** Rejected. It saves a
network hop and costs the single enforcement point, because the scope
dependency lives at the HTTP boundary. Reimplementing it inside the MCP server
is exactly the defect ISS-009 describes.

## Packaging: a second process in the API image

Added 2026-08-23, closing AUDIT-001 finding A001-F08.

The MCP server ships as a **second process in the `meter-api` image**, selected
by the container command, not as a fourth image.

The audit found that MCP had been described as a separate deployable in the
plan while having no build job, no ECR repository and no scan path, which would
have placed it outside the pipeline scan and the provenance verification
entirely.

Two ways to close that. Add a fourth image with its own build, scan, signature
and repository. Or ship it in the image it already shares a dependency set with.

The second is chosen. The MCP server imports nothing the API does not already
import, so a separate image would duplicate the entire dependency tree for one
module. It also inherits the scan, the SBOM, the signature and the attestation
for free, and every artefact added to a supply chain is one more thing to keep
at zero findings.

```
meter-api image
  ENTRYPOINT ["/opt/venv/bin/python", "-m"]
  CMD        ["finops_api.main"]              # the API service
  command    ["finops_mcp.server"]            # the MCP service, ECS override
```

Two ECS services, one image, one scan, one signature. The import linter
contract added in the same change prevents the shared image from becoming a
shared implementation.

## Scope by sub project

The MCP server grows with the product rather than arriving all at once.

| Sub project | Tools exposed |
| --- | --- |
| P0 | `list_accounts`, `get_org_tree`, `get_ingest_status`, `get_platform_cost` |
| P1 | `query_cost`, `get_cost_trend`, `explain_cost_change` |
| P2 | `list_expensive_queries`, `get_dashboard_cost` |
| P3 | `list_recommendations`, `get_savings_summary` |
| P4, P5 | `find_resource`, `get_topology`, `get_quota_headroom` |
