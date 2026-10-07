# ADR-0032: A row a person may share is read by its owner and, once shared, by the tenant

Date: 2026-10-07
Status: Accepted
Supersedes: nothing
Relates to: ADR-0029, whose rule this widens for one kind of row, and constraint 3

## Context

A saved view, FEAT-068, belongs to the person who saved it, as a question to the assistant
does, and the P8 spec's section 5.6 asks that its owner may share it with the tenant. ADR-0029's
`ByPrincipal` rule reads a person's row for that person alone, so a shared view could not be read
through it, and the tenant rule would show every private view to everybody in the tenant.

What makes sharing safe is what a view holds. It is a screen and its query string under a name,
and no figure. Nothing a view stores is an answer, so opening one reads the screen afresh in the
opener's own scope: a view saved by a reader of the whole estate and shared with a colleague
narrowed to two accounts shows that colleague their two accounts. Sharing a view shares a
question, not an answer.

## Decision

**The guard gains a fifth rule, `OwnedOrShared`.** A row under it is read by its owner, and by
everybody in its tenant once its visibility column says it is shared. It is applied before the
global check, as `ByPrincipal` is, so a reader of the whole estate reads a colleague's private
view no more than they read a colleague's questions. A scope with no principal reads nothing,
the fail closed case.

Writes are the owner's alone. The repository's write statements carry the scope predicate and
the owner's identifier together, so a route that forgot to check ownership would still change
nothing, and every write, refused or not, writes an audit row in the write's own transaction.

A shared view does not name who saved it to the people it is shared with. The answer says only
whether the reader owns it.

## What it costs

The rule is safe only for rows that hold configuration. A shared row is read across every
account boundary in the tenant, so a table holding a figure, or anything a person wrote that
the rest of the tenant should not read, must never be given this rule. The rule's docstring
says so as well as this record.

## Why this is an ADR

It decides who may read rows that belong to a person, and reversing it means either withdrawing
views people have shared with each other or reading private views that were saved on the
understanding that nobody else would.

## Consequences

- `finops_api/guards.py` holds `OwnedOrShared`, and `saved_view` is scoped by it.
- `finops_api/db/repositories/views.py` confines every write to the owner as well as to the
  scope, and audits each one, ALLOWED or DENIED.
- `tests/api/test_saved_views.py` asserts that a private view is its owner's alone even to an
  organization wide reader, that a shared one is opened by a colleague narrowed to one account,
  that a refused change leaves its audit row behind, and that opening a view reads its screen
  in the opener's scope, with two principals.
