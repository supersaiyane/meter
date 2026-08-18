# FEAT-042: Assistant bot

| Field | Value |
| --- | --- |
| Sub project | P7 |
| Status | Planned |
| Specification | Not written. This document expands when P7 is specified |
| Tasks | Not planned |
| Refresh cadence | Live |

## What it does

A conversational interface, in the product and through any MCP client, that can find anything in the tool: an account, a resource, a cost, a recommendation, a quota, a dashboard.

## Why it exists

Requested directly. Meter holds a lot of data across eight subsystems, and a search box that only searches one of them is not useful.

## What is already known

The MCP server is the bot's backend, see ADR-0009. It calls the same HTTP API with the caller's token, so scope filtering, the audit log and rate limiting apply unchanged and cannot be bypassed by adding a tool. Every answer carries provenance and the measured or modelled flag of each figure it cites.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P7 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P7.
