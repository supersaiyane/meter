# Change control

Last updated: 2026-08-23
Update trigger: any change to the process itself

The purpose of this document is narrow and specific: **every change must have
exactly one obvious home, and `INDEX.md` must always be able to find it.**

When a change has no obvious home, it gets recorded in a chat message, a commit
body, or nowhere. Three weeks later nobody can reconstruct why the system works
the way it does, so it gets re invented, incorrectly. That is the failure this
process exists to prevent.

## Generated versus hand written

Before the routing rule, know which half of the documentation a change belongs
in. See ADR-0014.

| Generated. Never hand edit | Hand written. Carries reasoning |
| --- | --- |
| `INDEX.md` sections 2 to 6 | `INDEX.md` prose sections |
| `docs/01-ROADMAP.md` status table | The roadmap's sub project descriptions |
| `tasks/STATUS.md` summary | The status task lists |
| Feature document header tables | Feature document bodies |
| `docs/architecture/file-graph.md` | ADRs, specs, plans |
| `security/POSTURE.md` | `docs/05-SECURITY.md`, `docs/07-DATA-MODEL.md` |
| `context_index.md` | `tasks/lessons.md`, `docs/checkpoint.md` |

A status change is **one line in `docs/registry.yaml` plus `make doc-sync`**.
It is never fifteen minutes of finding every place the old status was written.

## The routing rule

Read the change, answer the first question that applies, and stop.

| If the change is | It goes in | And you also |
| --- | --- | --- |
| A decision that is expensive to reverse | A new ADR in `docs/adr/` | Add a row to the ADR table in `INDEX.md` |
| A change to what a sub project delivers | That sub project's spec in `docs/specs/` | Update the feature row in `INDEX.md`, add a CHG row |
| A change to how a sub project is built | That sub project's plan in `docs/plans/` | Add a CHG row in `INDEX.md` |
| A new capability | A feature row in `INDEX.md`, and the owning spec | Update `docs/01-ROADMAP.md` if it changes scope |
| A defect, risk, or gap | `docs/registry.yaml`, then `make doc-sync` | Nothing else. `tasks/ISSUES.md` and `INDEX.md` are generated |
| An audit finding | A report in `audits/`, then promote it to `docs/registry.yaml` | Never track a finding only in a report. Reports are snapshots and are never edited after publication |
| A question awaiting a person | An OPEN row in `tasks/ISSUES.md` | Add it to `INDEX.md` open questions |
| Cross cutting architecture | `docs/02-ARCHITECTURE.md` | Raise an ADR if it is expensive to reverse |
| Deployment or pipeline | `docs/04-DEPLOYMENT.md` | Add a CHG row in `INDEX.md` |
| A feature, decision, change, issue or open question status | `docs/registry.yaml` | Run `make doc-sync`. Nothing else |
| Progress on existing work | `tasks/STATUS.md` task lists | Nothing else |
| A database schema change | `docs/07-DATA-MODEL.md`, in the same commit as the migration | Add a CHG row to the registry |
| A rung disqualification | An ADR with the full trail | See ADR-0013 |
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
4. **Never fill a commit reference by amending the commit it names.** Amending
   changes the SHA, so the reference is wrong again immediately. Record it in
   the next commit instead, which is why rows like CHG-0003 and CHG-0016 are
   completed one commit later.
5. **Never leave `INDEX.md` behind.** It is the only document a newcomer is
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
| `A<nnn>-F<nn>` | An audit finding | `audits/`, promoted to an `ISS-nnn` |

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

## A specification is not approvable without exit criteria

Every specification carries a "Definition of done" section, and it must satisfy
the seven universal exit criteria in `docs/01-ROADMAP.md` plus the criterion
specific to that sub project. A specification without them cannot be approved,
because a sub project with no exit criteria ends when someone decides it feels
finished. AUDIT-001, finding A001-F17.

## Update cadence: four tiers

The question "how often do all these documents get updated" has four answers,
because four different things change at four different rates. Automation covers
the first two entirely.

### Tier 1: every commit, automatic

Regenerated by `make doc-sync`, enforced by `make check-docs` in the pipeline.
**Zero human effort.**

`INDEX.md` sections 2 to 6, the roadmap status table, the status summary,
feature document headers, the file graph, `security/POSTURE.md`,
`context_index.md`.

### Tier 2: every commit, enforced

Not generated, but a commit fails without them.

| Trigger | Document | Enforced by |
| --- | --- | --- |
| A feature changes | `docs/registry.yaml` and the feature body | `check_feature_docs.py` |
| A dependency is added | `security/` scan artefacts | `make security-scan` in `verify` |
| A module moves | `project_map.md` | Review, plus the file graph |
| A schema changes | `docs/07-DATA-MODEL.md` and an Alembic revision | `test_no_pending_autogenerate` |

### Tier 3: every task, and every session

By hand, prompted by `make session-end`.

| Trigger | Document |
| --- | --- |
| A task reaches a terminal state | `tasks/STATUS.md`, and the task's evidence field |
| End of a work session | `docs/checkpoint.md`, with a resume vector |
| A correction is received | `tasks/lessons.md` |
| An issue is found or closed | `docs/registry.yaml` and `tasks/ISSUES.md` |

### Tier 4: every phase

At the end of each sub project, and no more often.

| What | Why |
| --- | --- |
| Reconcile the registry against reality | Generated views are only as true as their source |
| Review every ADR for supersession | A decision that no longer holds is worse than no decision |
| Archive `docs/checkpoint.md` past 50 entries | Keep the resume path short |
| Walk every OPEN issue and open question | Chase or close each one |
| Re measure: is any document unread | An unread document is a candidate for deletion, see ADR-0014 |

### Weekly

Walk the OPEN rows in the registry. Chase or close each one. This is the only
recurring calendar item, because open questions are the one thing automation
cannot resolve.
