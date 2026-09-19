# FEAT-049: Configuration and feature flags

| Field | Value |
| --- | --- |
| Sub project | P0 |
| Status | Specified |
| Specification | [ADR-0017](../adr/ADR-0017-configuration-and-feature-flags.md), `.env.example` |
| Tasks | TASK-P0-034 |
| Decisions | ADR-0017 |
| Issues addressed | ISS-088, ISS-087 |
| Refresh cadence | Environment at deploy. Runtime flags cached 60 seconds |

## What it does

Puts every value the application reads into one typed settings object, and
makes any feature switchable without a deploy.

## Why it exists

Two requirements given together, and they pull against each other if you are
not careful. Make as much switchable as possible, and hardcode nothing.

The switchability requirement has a well known failure mode: a codebase
acquires two hundred flags, every one is a branch that must be tested in both
states, and nobody dares remove any because nobody knows who relies on them.
So the design has to grant the switchability and prevent the accumulation.

## How it works

**One `pydantic-settings` class**, validated at startup. The process refuses to
start when a required value is missing or malformed, because a service that
starts broken and fails on the first request has turned a deployment error into
a production incident.

**Three kinds of value**, behaving differently. Configuration and tuning live
in the environment and change with a deploy. Feature flags live in a
`feature_flag` table, per tenant, and change with a row update.

The distinction that matters: **a threshold is not a feature flag.** Both are
configurable, but a threshold is always read while a flag creates a branch.
Only branches accumulate test surface, so only flags carry the extra rules.

**Every flag carries five fields** in `docs/feature-flags.yaml`: default,
owner, reason, expiry and removal plan. **An expired flag fails the build**,
the same mechanism as an expired security allowlist entry, deliberately,
because both solve the same problem: a temporary decision quietly becoming
permanent.

## Failure behaviour

A missing required value stops the process at startup with the variable named.
A malformed value does the same. An unknown flag key reads as its declared
default rather than raising, because a typo in a flag name should not take a
service down.

## Security considerations

No secret is ever a default in `.env.example`. Secrets come from Secrets
Manager, injected by the ECS task role. `METER_FEATURE_SCOPE_AUDIT` cannot be
false when `METER_ENV` is prod, and the check rejects it.

## Interface

`.env.example` documents every variable with what it is, what it does, and
which file consumes it. That last column is what makes the file useful a year
later. Two checks keep it honest: `check_flags.py` for the register, and
`check_hardcoded.py` for six patterns of literal in application code.

## Not doing

No third party flag service. Rejected at rung five of ADR-0013: another vendor,
another outbound dependency, another entry in the supply chain, and another
bill on the front page of a product about bills.
