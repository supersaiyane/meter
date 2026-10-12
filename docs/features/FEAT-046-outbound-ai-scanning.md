# FEAT-046: Outbound AI request scanning, redact or block secrets

| Field | Value |
| --- | --- |
| Sub project | P7 |
| Status | Delivered |
| Specification | [P7 spec](../specs/2026-09-28-p7-insight-and-llm-layer-design.md), section 6.3 |
| Tasks | TASK-P7-013 |
| Refresh cadence | Every request, inline |
| Source | Adopted from a competitive review on 2026-08-23 |

## What it does

Scans every request leaving for the language model provider, and redacts or blocks anything matching a secret pattern before it goes.

## Why it exists

Meter runs seven scanners and every one of them looks at what comes in: dependencies, images, the repository, infrastructure as code. Nothing looked at what goes out. In a financial services environment, a secret in a prompt is an exfiltration path with no control on it.

## What is already known

The same pattern set `gitleaks` uses, applied inline to the request body rather than to a repository. Policy is configurable per tenant between redact and block, and the default is **block**, because a redaction that misses is silent while a block that misfires is loud.

Every blocked or redacted request writes an `audit_event`. A control nobody can report on does not survive its first audit.

## How it works

**As built, 2026-10-04, TASK-P7-013.** `finops_query/redaction.py` scans every question
before anything else happens to it, ahead of the budget check and before any prompt is
built, with seven rules copied from gitleaks 8.30.1, the version `make security-scan` runs.
`private-key`, `aws-access-token`, `github-pat`, `gitlab-pat` and `stripe-access-token`
block, and `slack-webhook-url` and `jwt` redact. Each rule keeps gitleaks' entropy floor,
so a run of one repeated character is a pattern rather than a credential. A match is
replaced by `[redacted: rule-id]`, naming its own rule, and the question is stored and sent
in that form. A blocked question is refused with the gap SECRET, names the rule, and
reaches no model.

One deliberate difference from gitleaks: its allowlist for AWS's documented example key is
not applied, because a question is not documentation. A test runs the real gitleaks binary
over the same samples and asserts it reports each one under the same rule.

This differs from what was known before the spec in two ways. The action is set per rule
rather than by a per tenant policy: a credential that grants access blocks, and a pasted
token is redacted. And the record is a `redaction_event` row rather than an `audit_event`,
because the event belongs to the exchange it was found in and to the person who typed it,
ADR-0029.

**Amended 2026-10-12, ISS-085.** What the tools return is screened too, by the same rules,
before the model reads it: `finops_query/insight.py` replaces each secret in a tool's result, or
in a failing tool's message, with its rule's name, and records the hit on the exchange as
`withheld`. Every hit there is replaced, whatever the rule's action, because a credential in the
estate's data is not the asker's to rotate and their question is not refused for someone else's
tag. The asker's own screen still shows what the tool returned; only what leaves for the model is
screened. Each hit is recorded in `redaction_event` with `found_in = 'tool_result'`, migration
0046, beside the question's own hits, `found_in = 'question'`.

## Failure behaviour

A secret in a format none of the seven rules knows passes through. That is the residual
risk of any pattern scanner, stated rather than hidden. A match below a rule's entropy
floor is not treated as a secret, as in gitleaks.

## Security considerations

No column can hold the secret: not the text, a hash, its position or its length. The stored
question is the screened text. An error about figures in an answer reports how many rather
than which, because the digits may be part of a secret. Redaction finds credentials, not
personal data, ISS-226.

## Interface

`GET /assistant/redactions`, the asker's own events only, listed on the `/assistant`
screen.

## Not doing

**The rest of gitleaks' rules**, which are written for repositories rather than for questions.
Scanning what the tools return was here until 2026-10-12, on the ground that it is Meter's own
data under the asker's scope; ISS-085 held that it still leaves Meter, and a key typed into a tag
is a key, so it is screened now.

See [docs/11-COMPETITIVE-REVIEW.md](../11-COMPETITIVE-REVIEW.md) for where this came from.
