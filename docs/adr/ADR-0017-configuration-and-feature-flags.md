# ADR-0017: Nothing is hardcoded, and every flag has an expiry

Date: 2026-08-23
Status: Accepted

## Context

Two requirements, given together on 2026-08-23, and they pull in opposite
directions if you are not careful.

1. Make as much as possible switchable, so a feature can be turned off without
   a deploy.
2. Do not hardcode values. Put them in configuration, documented, saying what
   each one is, what it does, and which file consumes it.

The first requirement has a well known failure mode. A codebase acquires two
hundred flags, nobody remembers what half of them do, every one is a branch
that must be tested in both states, and nobody dares remove any of them because
nobody knows who is relying on them. Combinatorial test surface, permanently.

So the decision has to grant the switchability and prevent the accumulation.

## Decision

### One settings object, typed, validated at startup

A single `pydantic-settings` class. Every value the application reads comes from
it. No `os.environ` anywhere else, and no literal region, account identifier,
URL, timeout or threshold in application code.

**Validated at startup, and the process refuses to start when a required value
is missing or malformed.** A service that starts with a broken configuration
and fails on the first request has turned a deployment error into a production
incident.

### Three kinds of value, and they behave differently

| Kind | Lives in | Changed by | Example |
| --- | --- | --- | --- |
| **Configuration** | Environment | A deploy | Database URL, regions, role names, timeouts |
| **Tuning** | Environment, with a documented default | A deploy | Severity thresholds, p95 window, batch sizes |
| **Feature flag** | `feature_flag` table, per tenant | A row update, no deploy | Whether the MCP server is exposed, whether a collector runs |

The distinction that matters: a **threshold is not a feature flag.** Both are
configurable, but a threshold is always read and a flag creates a branch. Only
the second one accumulates test surface, so only the second one carries the
extra rules below.

### Every feature flag carries five fields, or it is not merged

```yaml
- key: mcp_server_enabled
  default: false
  owner: name@example.com
  reason: >
    The MCP server is a second process on the API image. Off until the tool
    schemas are generated from the API models, see TASK-P0-030.
  expires: 2026-11-21
  removal: Delete the flag and the false branch once P1 tools ship
```

**`expires` is mandatory and enforced.** A flag past its expiry fails
`make check-flags` and therefore the build, exactly as an expired security
allowlist entry does. The two mechanisms are deliberately identical, because
they solve the same problem: a temporary decision quietly becoming permanent.

**`removal` is mandatory.** A flag with no plan for its own deletion is not
temporary, it is a permanent branch that has not admitted it yet.

### The rule that keeps the count down

**A flag is for something that must be switchable in production without a
deploy.** Not for something the author is unsure about. Uncertainty is resolved
by deciding, or by not building the thing.

Target is fewer than fifteen live flags. If the count grows past that, the
review is which ones have outlived their reason, not how to organise them
better.

### Enforcement

`scripts/ci/check_hardcoded.py` fails the build on a literal region, account
identifier, ARN, endpoint URL or bare numeric threshold in application code,
with an allowlist for the settings module itself and for tests. Documentation
alone does not prevent hardcoding, and this is the second time in this project
that a rule has needed a check to be real.

`.env.example` documents every variable: what it is, what it does, its default,
and **which file consumes it**. That last column is the one that makes the file
useful a year later, and it is checked against the settings class so it cannot
drift.

## Consequences

Positive.

- A collector can be disabled per tenant, at three in the morning, without a
  deploy. That is the actual requirement.
- Every tunable is visible in one file with its reasoning, so nobody greps the
  codebase for a magic number.
- The expiry mechanism means the flag count trends toward zero rather than
  upward, which is the opposite of what usually happens.

Negative.

- Every flag is a branch and both sides need testing. That cost is real, and it
  is why the bar for creating one is high.
- A per tenant flag read on a hot path needs caching, which is a cache that can
  be stale. Mitigated by a short TTL and by accepting that a flag change taking
  60 seconds to apply is fine.
- Startup validation means a missing variable stops a deploy. That is the
  intent, and it will be annoying exactly once per missing variable.

## Alternatives rejected

**A third party flag service.** Rejected at rung five of ADR-0013. It is
another vendor, another outbound dependency, another thing in the supply chain,
and another bill on the front page of a product about bills. A database table
and a 60 second cache covers this need entirely.

**Environment variables for everything, including flags.** Rejected. It fails
the actual requirement, which is switching a feature off without a deploy.

**Flags with no expiry, reviewed periodically.** Rejected. Periodic review of
flags is a task that is always less urgent than whatever else is happening. An
expiry that breaks the build is a review that actually occurs.
