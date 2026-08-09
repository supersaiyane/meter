# Change control

Last updated: 2026-08-23
Update trigger: any change to the process itself

The purpose of this document is narrow and specific: **every change must have
exactly one obvious home, and `INDEX.md` must always be able to find it.**

When a change has no obvious home, it gets recorded in a chat message, a commit
body, or nowhere. Three weeks later nobody can reconstruct why the system works
the way it does, so it gets re invented, incorrectly. That is the failure this
process exists to prevent.

## The routing rule

Read the change, answer the first question that applies, and stop.

| If the change is | It goes in | And you also |
| --- | --- | --- |
| A decision that is expensive to reverse | A new ADR in `docs/adr/` | Add a row to the ADR table in `INDEX.md` |
| A change to what a sub project delivers | That sub project's spec in `docs/specs/` | Update the feature row in `INDEX.md`, add a CHG row |
| A change to how a sub project is built | That sub project's plan in `docs/plans/` | Add a CHG row in `INDEX.md` |
| A new capability | A feature row in `INDEX.md`, and the owning spec | Update `docs/01-ROADMAP.md` if it changes scope |
| A defect, risk, or gap | A row in `tasks/ISSUES.md` | Add the issue to `INDEX.md` |
| A question awaiting a person | An OPEN row in `tasks/ISSUES.md` | Add it to `INDEX.md` open questions |
| Cross cutting architecture | `docs/02-ARCHITECTURE.md` | Raise an ADR if it is expensive to reverse |
| Deployment or pipeline | `docs/04-DEPLOYMENT.md` | Add a CHG row in `INDEX.md` |
| Progress on existing work | `tasks/STATUS.md` | Nothing else |
| A correction you received | `tasks/lessons.md` | Nothing else |
| A module added, moved or repurposed | `project_map.md` | Nothing else |
| A new or removed public symbol | `context_index.md` | Nothing else |
| Where a session stopped | `docs/checkpoint.md` | Nothing else |

If two rows seem to apply, take the higher one. If none apply, the change is
probably a defect in this table, so fix the table.

## Never do these

1. **Never edit an accepted ADR to change its decision.** Write a new ADR and
   mark the old one `Superseded by ADR-NNNN`. The history of what was believed
   and when is the whole value of the record.
2. **Never record a change only in a commit message.** Commits are not
   searchable by a person who does not already know what they are looking for.
3. **Never mark an issue FIXED because the design decided how to fix it.**
   FIXED in `tasks/ISSUES.md` means the decision is recorded. Implementation
   status lives only in `tasks/STATUS.md`. Conflating those two is how a
   tracker starts lying.
4. **Never leave `INDEX.md` behind.** It is the only document a newcomer is
   guaranteed to read.

## Identifier scheme

| Prefix | Meaning | Lives in |
| --- | --- | --- |
| `FEAT-nnn` | A capability the product provides | `INDEX.md`, detailed in a spec |
| `ADR-nnnn` | A decision that is expensive to reverse | `docs/adr/` |
| `CHG-nnnn` | A material change to the project | `INDEX.md` change log |
| `ISS-nnn` | A defect, risk or gap | `tasks/ISSUES.md` |
| `OPEN-nn` | A question awaiting a person | `tasks/ISSUES.md` |
| `TASK-Pn-nnn` | A unit of implementation work | `docs/plans/` |

Identifiers are never reused and never renumbered. A withdrawn item is marked
`WITHDRAWN` and kept.

## The anti hallucination contract

This section exists because implementation will be handed to an agent, and an
agent given an ambiguous instruction will invent a plausible answer rather than
stop. Every task document must therefore make invention unnecessary and
detectable.

Every task in `docs/plans/` carries all seven of these. A task missing any of
them is not ready to be worked.

1. **Implements.** The exact spec section it comes from, for example
   `P0 spec section 5.2`. If no spec section covers it, the spec is incomplete
   and must be updated first. Work never begins on an unspecified task.
2. **Files.** The exact files to create or change. Creating a file not on the
   list is a deviation and must be reported, not absorbed silently.
3. **Acceptance criteria.** Observable and checkable, phrased so that pass or
   fail is not a judgement call.
4. **Tests.** The named test cases that must exist and pass. Not "add tests".
5. **Depends on.** The task identifiers that must be complete first.
6. **Do not.** The specific wrong turns available at this task. This field is
   the highest value one, because it names the plausible mistake before it is
   made.
7. **Evidence.** The command to run and the output to paste. Reading the code
   back is not evidence.

### When reality does not match the plan

Stop. Do not improvise around it.

1. Write the mismatch as an `ISS-nnn` row in `tasks/ISSUES.md`.
2. If the spec is wrong, update the spec, add a `CHG-nnnn` row, and update
   `INDEX.md`.
3. Only then continue.

An agent that quietly works around a wrong specification produces code nobody
can review, because the document that was supposed to describe it no longer
does.

## Review cadence

| When | What |
| --- | --- |
| End of every work session | `tasks/STATUS.md`, `docs/checkpoint.md` |
| End of every task | The seven fields above are all satisfied, evidence pasted |
| Before every merge request | `make verify` passes, `INDEX.md` reflects the change |
| Weekly | Walk the OPEN rows in `tasks/ISSUES.md`, chase or close each one |
| At the end of each sub project | Reconcile `INDEX.md` against reality, and archive `docs/checkpoint.md` if it exceeds 50 entries |
