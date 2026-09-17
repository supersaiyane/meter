# FEAT-046: Outbound AI request scanning, redact or block secrets

| Field | Value |
| --- | --- |
| Sub project | P7 |
| Status | Planned |
| Specification | Not written. This document expands when P7 is specified |
| Tasks | Not planned |
| Refresh cadence | Every request, inline |
| Source | Adopted from a competitive review on 2026-08-23 |

## What it does

Scans every request leaving for the language model provider, and redacts or blocks anything matching a secret pattern before it goes.

## Why it exists

Meter runs seven scanners and every one of them looks at what comes in: dependencies, images, the repository, infrastructure as code. Nothing looked at what goes out. In a financial services environment, a secret in a prompt is an exfiltration path with no control on it.

## What is already known

The same pattern set `gitleaks` uses, applied inline to the request body rather than to a repository. Policy is configurable per tenant between redact and block, and the default is **block**, because a redaction that misses is silent while a block that misfires is loud.

Every blocked or redacted request writes an `audit_event`. A control nobody can report on does not survive its first audit.

## Status of this document

Planned. The remaining sections are written when P7 is specified. Recording
only what is decided is deliberate: a document that invents detail ahead of the
decision is worse than a short one, because it will be believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P7, and
[docs/11-COMPETITIVE-REVIEW.md](../11-COMPETITIVE-REVIEW.md).
