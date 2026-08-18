# FEAT-038: Natural language cost query

| Field | Value |
| --- | --- |
| Sub project | P7 |
| Status | Planned |
| Specification | Not written. This document expands when P7 is specified |
| Tasks | Not planned |
| Refresh cadence | Live |

## What it does

Ask a cost question in plain English and get an answer built from Meter's own typed APIs.

## Why it exists

The requirement asked whether a language model could help. This is where it genuinely does.

## What is already known

Tool calling against the MCP server, over a governed semantic layer. Never free form SQL against CUR, which is both a hallucination risk and a query cost risk inside a product built to prevent runaway query cost. See ADR-0007 and ADR-0009.

## Status of this document

Planned. The sections a specified feature carries, how it works in detail, its
data sources, its measured versus modelled figures, its failure behaviour, its
security considerations and its interface, are written when P7 is specified.
Recording only what is actually decided is deliberate: a document that invents
detail ahead of the decision is worse than a short one, because it will be
believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P7.
