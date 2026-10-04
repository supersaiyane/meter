# FEAT-042: Assistant bot

| Field | Value |
| --- | --- |
| Sub project | P7 |
| Status | Delivered |
| Specification | [P7 spec](../specs/2026-09-28-p7-insight-and-llm-layer-design.md), section 9 |
| Tasks | TASK-P0-030 delivered the MCP server. TASK-P7-010 and TASK-P7-011 the routes and the screen |
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

## How it works

**As built, 2026-10-04, TASK-P7-010 and TASK-P7-011.** The bot is the FEAT-038 loop behind
four routes and one screen. `POST /assistant/ask` takes a question of up to two thousand
characters and returns the exchange. `GET /assistant/exchanges` lists the asker's own,
`GET /assistant/redactions` lists what redaction found in their questions, and
`GET /assistant/digests` lists the digests, FEAT-041. The `/assistant` screen renders the
three outcomes as three different shapes: an answer whose every figure is a `Figure` in its
provenance treatment and traceable to the tool call that returned it, a refusal naming what
is missing and linking to the screen that would show it, and a failure naming its cause.
Each exchange shows its tokens and its modelled cost.

The find anything half of the name is that link. A question the assistant cannot answer
from a tool still names the screen where the answer lives, when there is one.

The tool table described above as it stood after P0 moved to `finops_api/tools.py` on
2026-10-04, CHG-0110, and now also carries the cost tools the assistant asks with. The
assistant runs inside the API process and its tool calls go back through the same
application, ISS-225, so the API composes it without importing the MCP facade.

## Failure behaviour

As FEAT-038. A deployment with no model configured shows not enabled, never an empty
answer and never a zero.

## Security considerations

An exchange and a redaction event belong to the person who asked, and the guard confines
them to that person even under a payer wide scope, ADR-0029. The month's token sum is the
one read across people, and it returns a number.

## Interface

The four routes and the screen above, and the MCP server, which publishes the same tool
table to any MCP client.

## Not doing

**Conversation.** Each question stands alone, with no history sent to the model. **A per
person limit**, OPEN-12. **The envelope behind a citation**, which spec section 9 asks for:
the screen shows the call and the path, and the exchange does not store the envelope,
ISS-231. **Separate screens for the history and the redaction events.** Both are lists on
`/assistant`.
