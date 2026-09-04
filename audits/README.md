# Audits

Point in time reviews of the project against its own stated rules. Reports are
committed so the position at any date is reconstructable.

An audit is not a status update. `tasks/STATUS.md` says what is done. An audit
says what is **wrong**, including things that look done and are not.

## Naming

```
AUDIT-<nnn>-<YYYY-MM-DD>-<scope>.md
```

| Part | Rule |
| --- | --- |
| `nnn` | Sequential from 001. Never reused, never renumbered |
| `YYYY-MM-DD` | Date the audit was performed, not the date it was written up |
| `scope` | One slug from the vocabulary below. Never invent one |

Sorting by filename gives chronological order, and grepping a scope gives the
history of that area. Both matter when there are thirty of these.

### Scope vocabulary

| Slug | Covers |
| --- | --- |
| `full-project` | Everything. Expensive, so reserved for milestones |
| `documentation` | Consistency, coverage, drift, dead references |
| `security` | Posture, gates, dependencies, images, secrets, IAM |
| `data-model` | Schema, constraints, migrations, invariants |
| `spec-p0` .. `spec-p7` | One sub project specification against its plan |
| `code` | Implementation against the spec it claims to implement |
| `infrastructure` | Terraform, pipeline, deployment, runtime |
| `dependencies` | Supply chain, licences, transitive tree, currency |
| `pre-release` | Readiness gate before a release |

## Finding identifiers

```
A<nnn>-F<nn>        for example  A001-F03
```

Stable inside the report. A finding that survives verification is **promoted**
into `docs/registry.yaml` as an `ISS-nnn`, so there is still exactly one issue
register. The audit report keeps the evidence, the registry keeps the state.

Never track a finding only in an audit report. Reports are snapshots and are
never edited after publication.

## Severity

Same vocabulary as the issue register, so a promoted finding does not change
meaning on the way across.

| Severity | Meaning |
| --- | --- |
| `CRITICAL` | Blocks delivery, or risks data loss or a security breach |
| `HIGH` | A real defect or a significant risk |
| `MEDIUM` | Maintainability or accuracy concern |
| `LOW` | Minor improvement |

## Verdict

Every report ends with one of three, and the reason.

| Verdict | Meaning |
| --- | --- |
| `BLOCK` | Do not proceed until the named findings are closed |
| `PROCEED WITH CONDITIONS` | Proceed, and close the named findings inside the stated window |
| `PROCEED` | No finding is material to the next step |

## Rules

1. **Every finding carries evidence**: a command, a file and line, or a quoted
   contradiction. A finding with no evidence is an opinion.
2. **Report what is right as well as what is wrong.** An audit that lists only
   faults cannot be calibrated, and gets discounted.
3. **Never edit a published report.** A correction is a new report that
   supersedes it, named in both.
4. **Findings are promoted, not duplicated.** The registry holds the state.

## Cadence

| Scope | When |
| --- | --- |
| `full-project` | Before the first line of code, then at each sub project boundary |
| `security` | Monthly, and before any release |
| `documentation` | At each sub project boundary |
| `code` | At the end of each sub project |
| `pre-release` | Before every release |

## Index

| Report | Date | Scope | Verdict | Findings |
| --- | --- | --- | --- | --- |
| [AUDIT-001](AUDIT-001-2026-08-23-full-project.md) | 2026-08-23 | full-project | PROCEED WITH CONDITIONS | 18 |
