# AUDIT-001: full project

| Field | Value |
| --- | --- |
| Date | 2026-08-23 |
| Scope | `full-project` |
| Trigger | Requested before the first line of application code |
| Reviewed | 119 tracked files, 77 documents, 13 scripts, 34 commits |
| Method | Mechanical checks plus manual reading. Every finding carries evidence |
| Verdict | **PROCEED WITH CONDITIONS** |
| Findings | 18. 1 critical, 5 high, 8 medium, 4 low |

## Verdict

**Proceed, on four conditions.** Nothing found undermines the architecture, and
the parts most likely to be wrong at this stage, the error taxonomy, the
scope enforcement design and the ingestion idempotency model, are internally
consistent and correctly reasoned.

But four things must close before code starts, because each one gets more
expensive the moment there is code to change.

1. **A001-F11**, no threat model. This is financial services, holding
   organization wide financial data and cross account credentials.
2. **A001-F12**, no data classification or retention policy, while the schema
   already stores account root email addresses.
3. **A001-F02**, `finops_mcp` is outside the import linter contract, so the one
   constraint that keeps multi cloud cheap is unenforced for that module.
4. **A001-F01**, the issue register has already drifted, which means the
   process meant to prevent drift is half installed.

The remaining fourteen can close during P0.

---

## What is right

Stated first, because an audit that lists only faults cannot be calibrated.

| Area | Evidence |
| --- | --- |
| Cross reference integrity | `make check-docs`: 80 references checked, 0 broken. 42 feature documents, all present and complete |
| Layering | `build_file_graph.py --check`: 19 files, 17 edges, 0 violations |
| Error taxonomy consistency | The six types in P0 spec section 6 match the `ck_ingest_run__error_type_valid` check constraint in `docs/07-DATA-MODEL.md` exactly. Adding a seventh requires a migration, which is the intended friction |
| Traceability | All 12 spec section references in the P0 plan resolve to real sections, including `8.0` and `11a`. Verified mechanically |
| Security gate chain | Six layers, and the two most commonly missing, provenance verification and the nightly digest scan, are both present |
| Invariants | Idempotency, `as_of` nullability and the closed enums are database constraints, not conventions |
| Honest limits | LocalStack, quota coverage at roughly 70 percent, and the AWS imposed freshness ceiling are all documented as limits rather than hidden |

The design decisions that would be expensive to get wrong are recorded with
their rejected alternatives, which is the part most projects skip.

---

## Findings

### A001-F11 `CRITICAL` No threat model

**Evidence.** `grep -ril "threat model" docs/` returns zero documents.

**Why it matters.** Meter will hold, for an entire AWS Organization: every
account identifier, the organization structure, cost data at resource
granularity, resource inventory, and the ability to assume a read role into
every member account. The deployment target is financial services.

There is a security **policy** (`docs/05-SECURITY.md`) and there are security
**controls**. There is no analysis of who would attack this, how, and which
control stops them. Those are different documents and the policy does not
substitute.

Specific questions currently unanswered: what does a compromised hub task role
give an attacker, and what bounds the blast radius; what stops a member account
administrator from using their own collector role against a different account;
what happens if the ExternalId leaks; what is the abuse case for the global
viewer credential; can an MCP client be induced to exfiltrate cost data through
the bot.

**Recommendation.** A STRIDE pass over the six trust boundaries, written to
`docs/08-THREAT-MODEL.md`, before code. Each mitigation references the control
that implements it, and each unmitigated threat becomes an issue.

---

### A001-F12 `HIGH` No data classification or retention policy, and the schema already holds personal data

**Evidence.** `docs/07-DATA-MODEL.md` line 172: `cloud_account.email TEXT`. That
is the AWS account root email address, which is personal data. Also
`principal.email`. `grep -ril "data classification\|GDPR\|PII" docs/` returns
zero documents. `retention` appears in three documents, all about CloudWatch log
retention as a cost lever, none about Meter's own data.

**Why it matters.** Three separate problems. There is no statement of what data
classes Meter holds and how each is handled. There is no retention period, so
`audit_event` and `cost_focus_daily` grow without bound and nothing says when
they may be deleted. And there is no erasure path, which a financial services
data protection review will ask about on the first day.

**Recommendation.** `docs/09-DATA-CLASSIFICATION.md` before code: the classes,
where each lives, retention per table, the erasure path, and the encryption and
access position for each. Then either drop `cloud_account.email` if nothing
needs it, or justify keeping it.

---

### A001-F02 `HIGH` `finops_mcp` is outside the import linter contract

**Evidence.**

```
pyproject packages:        ['finops_core', 'finops_providers', 'finops_ingest', 'finops_api']
importlinter root_packages: ['finops_core', 'finops_providers', 'finops_ingest', 'finops_api']
```

`finops_mcp` appears in `project_map.md`, `README.md`, `CLAUDE.md`,
`ADR-0009`, the P0 spec, the P0 plan, and the `LAYERS` list in
`scripts/docs/build_file_graph.py`. It is absent from both `pyproject.toml`
lists.

**Why it matters.** `CLAUDE.md` constraint 8 and ADR-0009 both state that the
MCP server must never reach into the service layer, because two implementations
of an authorization rule is how an authorization bug is created. That rule is
currently enforced by nothing. The moment `finops_mcp` exists, an import of a
repository will pass CI.

**Recommendation.** Add `finops_mcp` to `packages` and to `root_packages`, and
add a forbidden contract preventing it from importing `finops_api.db`,
`finops_providers` and `boto3`. One line each, before TASK-P0-030.

---

### A001-F01 `HIGH` The issue register has already drifted

**Evidence.**

```
registry: 51 issues     tasks/ISSUES.md: 29 issues
in registry only: ISS-033 through ISS-054   (22 issues)
in ISSUES.md only: none
```

**Why it matters.** ADR-0014 made `docs/registry.yaml` the single source of
truth and generated the derived views, specifically to make this impossible.
The feature tables, the roadmap status and the status summary were brought
under generation. `tasks/ISSUES.md` was not, and it carries the same
identifiers.

So the process meant to prevent drift is half installed, and the half that was
left out has drifted by 22 records inside a single session. That is the fastest
possible demonstration that the diagnosis in ADR-0014 was right.

**Recommendation.** Bring `tasks/ISSUES.md` under generation, keeping its
narrative sections hand written and its register block generated. **Fixed
during this audit**, see the note at the end.

---

### A001-F03 `HIGH` A pipeline security job cannot run

**Evidence.** `.gitlab-ci.yml`, the `.security_tools` anchor installs grype,
syft, trivy and pip-audit. The `dependency-scan` job uses that anchor and runs
`scripts/security/scan.sh`, which contains `require gitleaks` and exits 2 when
it is missing. `gitleaks` is installed only in the separate `secrets-scan` job,
which uses its own image.

**Why it matters.** The dependency scan is layer 4 of the security model, the
first layer that can actually stop a deploy. It would fail on tooling rather
than on a finding, and a job that always fails gets marked `allow_failure` by
the third person who hits it. That is how a gate quietly becomes decoration.

**Recommendation.** Add gitleaks to the `.security_tools` anchor, or make
`scan.sh` skip secret scanning with a loud warning when the binary is absent
rather than exiting 2. The first is better: a silent skip in the one job that
gates deploys is worse than a hard failure.

---

### A001-F05 `HIGH` `make verify` fails on a clean machine for the wrong reason

**Evidence.** `Makefile` line 343: `verify: lint check-writing check-docs test
security-scan`. `security-scan` runs `scan.sh`, which requires gitleaks,
pip-audit, and for image scanning grype, syft and trivy. `security-tools`, at
line 247, installs them and is a **separate manual target** that nothing
depends on.

**Why it matters.** A new engineer clones, runs `make setup`, runs
`make verify`, and gets a tooling error that reads like a security failure. The
first impression of the security gate is that it is broken. `make setup` is the
obvious place to install the tools and it does not.

**Recommendation.** Make `setup` depend on `security-tools`, and have `scan.sh`
print an explicit "install with `make security-tools`" line on a missing binary
rather than a bare "MISSING TOOL".

---

### A001-F04 `MEDIUM` The first `make up` on a clean clone fails

**Evidence.** `docker-compose.yml` line 84 mounts `./local-auth.yaml`.
`.gitignore` contains `local-auth.yaml`. The example file
`local-auth.example.yaml` is not created until TASK-P0-012.

**Why it matters.** Docker creates a directory when a bind mount source does
not exist, so the API starts with a directory where a config file should be and
fails in a confusing way. The first command a new engineer runs is the one that
breaks.

**Recommendation.** Commit `local-auth.example.yaml` now, and have `make up`
copy it to `local-auth.yaml` when that file is absent. Move the mount to the
example path if simpler.

---

### A001-F06 `MEDIUM` `context_index.md` is claimed generated and has no generator

**Evidence.** `ADR-0014` line 47 lists `context_index.md` as **Generated** from
source. `grep -rn "context_index" scripts/ Makefile` returns nothing. The file
is hand written and empty apart from a placeholder.

**Why it matters.** A document claimed to be generated will not be maintained
by hand, because everyone assumes a tool is doing it. It will be empty forever,
and rung two of the ADR-0013 ladder, "does it already exist in this
repository", tells engineers to check exactly this file first.

**Recommendation.** Either write the generator, an AST walk over the four
packages emitting symbol, file, line and callers, or remove the claim from
ADR-0014 and mark the file hand maintained. Writing the generator is cheap and
the file is load bearing for the ladder.

---

### A001-F07 `MEDIUM` The interactive file graph renders nothing

**Evidence.** `scripts/docs/build_file_graph.py` line 274 checks
`if (!window.cytoscape)` and prints a message. Nothing loads or vendors
cytoscape, and the content security posture rules out a CDN.

**Why it matters.** `docs/architecture/file-graph.html` is referenced from
`INDEX.md` and `README.md` as the interactive view. Opening it shows a header,
a node count, and an apology. The Mermaid version in `file-graph.md` works, so
the HTML adds nothing today.

**Recommendation.** Either vendor the cytoscape bundle into
`docs/architecture/vendor/` and wire it up, or delete the HTML output and point
only at the Mermaid version. Deleting is rung zero of the ladder and is the
honest choice until someone needs pan and zoom.

---

### A001-F08 `MEDIUM` The MCP server has no build, no registry and no scan path

**Evidence.** TASK-P0-030 lists `docker/Dockerfile.mcp` in its file list.
TASK-P0-016 provisions "Four ECR repositories: api, worker, web, cache".
`.gitlab-ci.yml` defines three `build:` jobs and three `scan:` jobs.
`docker-compose.yml` has no mcp service.

**Why it matters.** MCP is a fourth deployable. As written it would be built by
hand, pushed to a repository that does not exist, and never scanned or signed,
which puts it outside layers 4 and 5 of the security model entirely.

**Recommendation.** Decide now whether MCP is a separate image or a second
process in the API image. A second process is simpler and shares the
dependency set. Whichever, update TASK-P0-016, the pipeline and compose in the
same change.

---

### A001-F13 `MEDIUM` No disaster recovery position

**Evidence.** `grep -ril "disaster recovery\|RTO" docs/` returns zero. `RPO`
appears only as a substring of unrelated words.

**Why it matters.** Aurora has default backups, and a default is not a
decision. Nothing states the recovery point objective, the recovery time
objective, whether the S3 raw exports are the recovery source for the warehouse,
or whether restore has ever been tested. A financial services review asks all
four.

There is a mitigating fact worth stating: Meter is a derived data system. Every
fact can be re ingested from AWS. That makes the objectives easier to meet, and
it should be written down as the strategy rather than assumed.

**Recommendation.** A short section in `docs/02-ARCHITECTURE.md`: RPO, RTO, what
is re ingestible and what is not, and a restore test in the P0 exit criteria.

---

### A001-F14 `MEDIUM` No observability plan for Meter itself

**Evidence.** `docs/02-ARCHITECTURE.md` and the P0 spec cover self metering,
which is cost. Nothing covers Meter's own logs, metrics, traces, alerts or on
call.

**Why it matters.** The ingestion framework fans out across hundreds of
accounts. When it silently stops collecting for one account, `sync_error` and
the freshness screen surface it **to a user who happens to look**. Nothing
pages anyone. A FinOps platform that stops collecting is worse than one that is
down, because it keeps serving confident stale numbers.

**Recommendation.** Define three or four SLOs and their alerts before P0 exits.
The obvious ones: ingestion freshness per collector, run success rate, API p95
latency, queue depth. Add a "collection has not advanced in N cadences" alarm,
which is the one that catches the failure that matters.

---

### A001-F15 `MEDIUM` No cost estimate for running Meter

**Evidence.** `platform_cost` and FEAT-008 measure the cost after the fact.
Nothing estimates it beforehand. `grep` finds no forecast in any document.

**Why it matters.** This is a FinOps product. Being unable to state its own
running cost before it runs is the specific credibility failure it exists to
prevent in others. There are also two genuinely uncertain line items already
identified as risks, AWS Config recording (ISS-012) and Cost Explorer request
volume, and neither has a number.

**Recommendation.** A one page estimate in `docs/04-DEPLOYMENT.md`: Fargate,
Aurora, NAT free VPC endpoints, S3, Athena scanned bytes, Cost Explorer
requests, CloudWatch `GetMetricData`, at the 50 account and 300 account points.
Rough is fine. Absent is not.

---

### A001-F16 `MEDIUM` Missing repository governance files

**Evidence.** All absent: `LICENSE`, `CODEOWNERS`, `SECURITY.md`,
`CONTRIBUTING.md`, `.editorconfig`, `CHANGELOG.md`.

**Why it matters.** Varies by file. `CODEOWNERS` is the one that matters most
here: `docs/05-SECURITY.md` requires a security sign off for a CVE triggered
rung escalation (ADR-0013), and nothing defines who can give it. `SECURITY.md`
defines the vulnerability disclosure route, which a financial services review
expects. `.editorconfig` would have prevented at least one class of the em dash
problem by disabling smart substitution.

**Recommendation.** `CODEOWNERS` and `.editorconfig` now, both trivial.
`SECURITY.md` before anything is exposed. `LICENSE` when the licensing position
is decided. `CHANGELOG.md` is unnecessary, the change register covers it.

---

### A001-F09 `LOW` `PARTIAL` ingest status is undefined

**Evidence.** `docs/07-DATA-MODEL.md` line 242 permits
`status IN ('CLAIMED','RUNNING','SUCCEEDED','FAILED','PARTIAL')`. `PARTIAL`
appears nowhere else in any document.

**Why it matters.** The whole error design turns on a user being able to
distinguish states. An undefined fifth state will be applied inconsistently by
whoever writes the first collector, and the freshness screen has no rule for
rendering it.

**Recommendation.** Define it in the P0 spec section 6, or remove it. A
suggested definition: the run completed and wrote some rows, but at least one
scope inside it produced a typed error. If that is right, the freshness screen
must render it as degraded, never as success.

---

### A001-F10 `LOW` The roadmap carries two statuses for the same sub project

**Evidence.** `docs/01-ROADMAP.md` line 41 is inside the generated block:
`| P0 | Foundation | 10 | 10 | 0 |`. Line 56 is hand written:
`| P0 | Foundation | Design approved, spec in review | ... |`.

**Why it matters.** The same drift as A001-F01, smaller. Two tables, one
generated and one not, describing the same thing.

**Recommendation.** Add `status`, `spec` and `plan` fields to the sub project
records in the registry and generate the second table too.

---

### A001-F17 `LOW` No definition of done beyond P0

**Evidence.** The P0 spec has a "Definition of done" section. No other sub
project has one, and no document defines when the **project** is done.

**Why it matters.** `docs/00-GOAL.md` has seven success criteria, which is
closer than most projects manage. But without per sub project exit criteria,
each one ends when someone decides it feels finished.

**Recommendation.** The specification template already has the section. Enforce
it when each spec is written. No action now.

---

### A001-F18 `LOW` No performance budget

**Evidence.** ADR-0003 names a single number, p95 dashboard latency above 1.5
seconds, as the trigger to revisit the serving layer. Nothing else is stated.

**Why it matters.** No budget for ingestion throughput, for the time to a full
organization sweep at 300 accounts, or for the API under concurrent users. The
first two are the ones that will bite, because they determine whether the
hourly cadence in ADR-0012 is achievable at all.

**Recommendation.** State two numbers in the P0 spec: a full `org_tree` and
`account_health` sweep of 300 accounts inside 15 minutes, and API p95 under 500
milliseconds on pre aggregated rollups. Then measure them in TASK-P0-028.

---

## Recommended order

Before the first line of code:

| Order | Finding | Effort |
| --- | --- | --- |
| 1 | A001-F02, add `finops_mcp` to the import linter contract | minutes |
| 2 | A001-F03, add gitleaks to the CI tool anchor | minutes |
| 3 | A001-F05, make `setup` install the security tools | minutes |
| 4 | A001-F04, commit `local-auth.example.yaml` and copy it in `make up` | minutes |
| 5 | A001-F16, `CODEOWNERS` and `.editorconfig` | minutes |
| 6 | A001-F08, decide whether MCP is a separate image | one decision |
| 7 | A001-F09, define or remove `PARTIAL` | one decision |
| 8 | **A001-F11, the threat model** | half a day |
| 9 | **A001-F12, data classification and retention** | half a day |
| 10 | A001-F13, the disaster recovery position | an hour |
| 11 | A001-F15, the cost estimate | an hour |

During P0: A001-F06, A001-F07, A001-F10, A001-F14, A001-F18.
No action now: A001-F17.

Items 8 and 9 are the two that get materially more expensive after code exists,
because both can change the schema.

---

## Fixed during this audit

**A001-F01.** Adding eighteen findings to the issue register would have widened
the drift this finding describes. `tasks/ISSUES.md` was brought under
generation in the same change, so its register block now comes from
`docs/registry.yaml` and the identifiers cannot diverge again.

No other finding was fixed. Fixing is a separate decision from reporting, and
mixing the two makes an audit unreadable.

---

## Method

| Check | Command |
| --- | --- |
| Cross references | `make check-docs` |
| Layering | `scripts/docs/build_file_graph.py --check` |
| Writing rules | `make check-writing` |
| Register drift | Set difference between `docs/registry.yaml` and `tasks/ISSUES.md` |
| Spec traceability | Regex extraction of every `P0 spec section N` reference, resolved against the spec headings |
| Package contracts | `pyproject.toml` parsed, compared against every module named in the documents |
| Governance files | Existence check on the conventional root files |
| Coverage of a topic | `grep -ril` across `docs/`, with substring false positives verified by hand |

Everything above is reproducible. No finding rests on an opinion about style.
