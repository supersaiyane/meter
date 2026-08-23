# ADR-0014: Derived documentation is generated from a registry, not hand maintained

Date: 2026-08-23
Status: Accepted

## Context

The project was asked, fairly, whether its documentation had become overkill.

The honest answer was yes in one specific way, and no in another.

**Not overkill:** the documents that carry reasoning. Specs, ADRs, plans,
feature bodies, the data model, the security policy. Each one is read when a
question arises, and each exists because a decision would otherwise be lost.

**Overkill:** the same fact maintained by hand in four places. Feature status
lived in the index feature table, the roadmap status table, the status tracker
and each feature document's own header. Four copies of one fact means a
guaranteed drift, and every session spent time re synchronising them.

The drift was not hypothetical. Building a machine readable registry from the
existing index immediately found six change log rows missing a column, which no
reader had noticed.

There is also a context cost. Research from a prior project on context rot and
the U shaped attention curve is directly relevant: past a point, more context
degrades rather than improves an agent's work. A documentation set that must be
read in full to be useful is a liability, and the mitigation is progressive
disclosure, one entry point that drills down, rather than volume reduction for
its own sake.

## Decision

**`docs/registry.yaml` is the single source of truth** for features,
decisions, changes, issues and open questions. Everything derived from those
facts is generated.

| Artefact | Hand written or generated |
| --- | --- |
| `docs/registry.yaml` | Hand written. The only place a status changes |
| `INDEX.md` tables | **Generated** between markers, prose kept |
| `docs/01-ROADMAP.md` status table | **Generated** between markers |
| `tasks/STATUS.md` summary | **Generated** between markers |
| Feature document header table | **Generated**, body hand written |
| `docs/architecture/file-graph.md` | **Generated** |
| `security/POSTURE.md` | **Generated** |
| `context_index.md` | **Generated** from source |
| ADRs, specs, plans, feature bodies, the data model, the security policy | Hand written. These carry reasoning, which cannot be generated |

`make doc-sync` regenerates everything. `make check-docs` fails when a
generated file differs from what would be generated, so a hand edit to a
generated block is caught rather than silently overwritten later.

## Consequences

Positive.

- One fact, one place. Drift becomes impossible rather than merely detectable.
- Maintenance surface drops from roughly fifty files to five, without deleting
  a single document. The 32 planned feature documents cost nothing to maintain
  now, because their headers regenerate and their bodies do not change until
  their sub project is specified.
- A status change is one line in a YAML file plus one command, not fifteen
  minutes of finding every place the old status was written.
- Adding a feature or an issue is mechanical, so it actually gets done.

Negative.

- A generated file must never be hand edited, and someone will try. The check
  catches it, and every generated block carries a header saying so.
- `registry.yaml` becomes a merge conflict point on a busy branch. Acceptable,
  and the conflicts are trivially resolvable because the file is a list.
- One more tool between a person and the documentation. Mitigated by
  `make doc-sync` being a single command that runs in under a second.

## Alternatives rejected

**Delete the planned feature documents.** Tempting, and wrong. They are where
the reasoning lands when a sub project is specified, and creating them at that
point would mean the index promises a document that does not exist. Generating
their headers costs nothing and solves the actual complaint, which was
maintenance burden, not existence.

**Keep hand maintaining everything and rely on `check_index.py`.** Rejected. A
check tells you the documents disagree, it does not tell you which one is
right, and it still costs a person the reconciliation every session.

**Put everything in one file.** Rejected. It works against progressive
disclosure: a reader looking for one fact would load everything, which is the
context rot problem in a different shape.
