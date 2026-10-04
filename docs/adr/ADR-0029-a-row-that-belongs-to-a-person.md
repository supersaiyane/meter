# ADR-0029: A row that belongs to a person is scoped by that person

Date: 2026-10-04
Status: Accepted
Supersedes: nothing
Relates to: ADR-0009 and constraint 3, which put scope in two places, and ADR-0028

## Context

Every table the guard knew before P7 holds a fact about a cloud account, or about the whole
payer, or about Meter's own runs. `SCOPED_TABLES` has a rule for each of those: a row names
its account, inherits one through another row, belongs to the payer, or belongs to the
tenant and nothing narrower.

`assistant_exchange` is the first table whose row belongs to a person. A question is the
asker's own words, written about whatever they were working on, and it can name a
customer, a project or a colleague as easily as a service. None of the existing rules says
anything about a person. Reusing one would have been wrong in a quiet way: the tenant rule
would show every question to every reader in the tenant, and no account rule applies,
because a question has no account.

## Decision

**The guard gains a fourth rule, `ByPrincipal`, and a row under it is read only by the
principal who wrote it.** `Scope` carries the principal it was resolved for, stamped by the
request dependency from the authenticated session, so the repository guard can apply the
rule without trusting the route to remember it.

Three consequences are deliberate:

- **A global scope does not widen it.** An organization wide reader sees every account's
  bill and none of their colleagues' questions. Reading somebody else's questions is a
  different permission from reading the estate, and nobody has granted it.
- **A scope with no principal reads nothing.** The same fail closed rule as a scope naming
  no accounts. A code path that builds a scope by hand and forgets the person gets an empty
  answer rather than everybody's.
- **The monthly budget sum is the one read that crosses people,** and it returns a number
  and never a row. The budget is per tenant, TASK-P7-007, so it must count everybody's
  spend, and a count is all it needs.

## What it costs

An owner cannot audit what their colleagues asked the assistant through the product. If
that need is real, it is a new permission with its own ADR, its own audit row and a screen
that says whose questions are being read, not a widening of this rule.

## Why this is an ADR

It decides who may read what a person typed, which is personal data in the plain sense, and
reversing it means deciding that one person may read another's words after they were
written on the understanding that they would not.

## Consequences

- `finops_api/guards.py` holds `ByPrincipal`, and `assistant_exchange` is scoped by it.
- `finops_core.domain.tenant.Scope` carries an optional `principal_id`, stamped by
  `finops_api.deps.get_scope`.
- `tests/api/test_assistant_routes.py` asserts one person cannot read another's questions,
  including with an organization wide scope.
