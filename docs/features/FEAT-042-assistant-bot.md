# FEAT-042: Assistant bot

| Field | Value |
| --- | --- |
| Sub project | P7 |
| Status | Planned |
| Specification | Not written. This document expands when P7 is specified |
| Tasks | TASK-P0-030 delivered the server and six read tools. The bot itself is not planned |
| Refresh cadence | Live |

## What it does

A conversational interface, in the product and through any MCP client, that can find anything in the tool: an account, a resource, a cost, a recommendation, a quota, a dashboard.

## Why it exists

Requested directly. Meter holds a lot of data across eight subsystems, and a search box that only searches one of them is not useful.

## What is already known

The MCP server is the bot's backend, see ADR-0009. It calls the same HTTP API with the caller's token, so scope filtering, the audit log and rate limiting apply unchanged and cannot be bypassed by adding a tool. Every answer carries provenance and the measured or modelled flag of each figure it cites.

## What exists now

TASK-P0-030 built the server, in `finops_mcp/`. It is a facade and holds no credential of its own.

| Tool | Route it calls |
| --- | --- |
| `list_accounts` | `/api/v1/accounts` |
| `get_org_tree` | `/api/v1/org/tree` |
| `get_ingest_status` | `/api/v1/ingest/runs` |
| `get_platform_cost` | `/api/v1/platform/cost` |
| `get_freshness` | `/api/v1/health/freshness` |
| `whoami` | `/api/v1/me` |

`get_freshness` and `whoami` are beyond the four the P0 spec names. Both exist for the same reason: the first question a model should ask about a partial or stale answer is what it is allowed to see and how old the data is, and without a tool for each the only way to find out is to infer it from a coverage fraction, which is guessing.

Each tool is a row in a table rather than a hand written handler, and the schema it advertises is generated from the same Pydantic model the route declares. A test holds each row against that route's own `response_model`, so a field added to the API without touching the tool table fails the build.

The response is returned as the API sent it, envelope included. A tool that returned only `data` would strip `scope_coverage` and `as_of`, and a model with no coverage figure states a partial total as an organization total, confidently. That is row I of the threat model.

It ships as a second process in the `meter-api` image, selected by the container command, and is served by the same uvicorn as the API. There is no fourth image, because a fourth image needs its own build, scan, signature and repository, which is how a deployable ends up outside the security gates.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P7 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P7.
