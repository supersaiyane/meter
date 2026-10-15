# P15 Fixes through pull requests: implementation plan

Date: 2026-10-15
Status: Approved by the owner on 2026-10-15 with OPEN-13 and OPEN-41 to OPEN-43 answered, in build
Spec: `docs/specs/2026-10-15-p15-pull-request-fixes-design.md`
Depends on: P3, P4, P7, P9, P12 and P13. Proof against a real repository waits on a GitHub App installation
Tasks: 9

Meter writes the fix for eight kinds of waste as a Terraform change and has never opened one,
because no code host stands behind the port. This sub project connects a GitHub App, opens the fix
in the repository whose Terraform manages the resource, adds gp2 to gp3 as an edit to the file that
declares the volume, follows each pull request until the inventory sees the change, and, under a
policy the tenant turns on, merges a fix that loses nothing if it is wrong.

## How to work this plan

Same contract as P0 through P14. One task, one commit, `make verify` green before a merge into
main, and main pushed after every merge.

**Three rules specific to P15.**

1. **Meter merges a reversible fix and nothing else.** The reversible set is in the domain and
   holds gp2 to gp3 alone; a database check keeps every other class out of a merge policy; one
   function performs the merge, and the contract test refuses the word anywhere else, ADR-0038.
   Meter never approves and never applies.
2. **Only the worker reaches GitHub.** The API records what a person asks for, and the
   `fix_pull_requests` collector acts on it, ADR-0036. The app's key is read from
   `meter/<env>/codehost/` and no token is stored.
3. **Merged is not done.** A recommendation is done when the inventory sees its change, and
   FEAT-029 measures the saving from the bill afterwards.

## Wave overview

| Wave | Tasks | Delivers | Can start when |
| --- | --- | --- | --- |
| A. The rule and the host | 001, 002 | The reversible set, the merge rule, the GitHub App adapter | This plan approved |
| B. Where a fix goes | 003 | The connection and the repository mapping | A |
| C. Opening and following | 004, 005, 006 | Removals opened, gp2 to gp3 as an edit, each pull request followed to done | B |
| D. Merging | 007 | The merge policy and Meter's merge | C |
| E. The screens and the proof | 008, 009 | The fix on the recommendation, the settings, the local stack, the exit criteria | D |

Modelled at the pace of P14: eight tasks of size M and one of size S, about nine working days.

---

### TASK-P15-001: the reversible set, the merge rule and the port

| Field | Value |
| --- | --- |
| Status | Done 2026-10-15 |
| Implements | Spec sections 5.2 and 9, ADR-0038 |
| Delivers | FEAT-094 |
| Depends on | Nothing |
| Estimate | S |

**Acceptance criteria.**

- [x] The domain holds the reversible set, `EBS_GP2_TO_GP3` alone, and a pure merge rule deciding
      from the policy, the class, who opened it and GitHub's report whether Meter may merge
- [x] The code host port gains reading a folder's files, reading a pull request's state and
      merging, each with its typed failures
- [x] The contract test allows the merge call in the one merge function only, and still refuses
      approval, applying and every tool that changes a cloud

**Delivered 2026-10-15.** `finops_core/domain/fixes.py` holds `REVERSIBLE`, `EBS_GP2_TO_GP3`
alone, and `may_merge`, which says yes only when merging is on, the class is reversible and named by
the policy, Meter opened the pull request, it is still open and the repository reports it ready;
every no says why. `finops_core/ports/pull_requests.py` gains `RepositoryTarget`,
`RepositoryReader.read_folder` and `PullRequestTracker.pull_request_state`, each naming its typed
failures. Merging is its own port, `finops_core/ports/merges.py`, and its one caller is
`finops_ingest/fix_merge.py`, which asks the rule first and merges at the head the host reported.
`tests/contract/test_no_llm_writes.py` allows the merge's name in those modules and the adapter only,
and checks by the syntax tree that nothing else calls it. Building it found ISS-299: a removal file
sat in a folder Terraform never reads, and now goes in the folder whose Terraform declares the
resource. Tests in `tests/core/test_fixes.py` and `tests/ingest/test_fix_merge.py`; both new modules
are at 100 percent coverage, measured.

---

### TASK-P15-002: the GitHub App adapter

| Field | Value |
| --- | --- |
| Status | Done 2026-10-15 |
| Implements | Spec sections 5.1 and 9, OPEN-13 |
| Delivers | FEAT-040, FEAT-091 |
| Depends on | TASK-P15-001 |
| Estimate | M |

**Acceptance criteria.**

- [x] A token is minted per request from the app's key, read from `meter/<env>/codehost/` only by
      the worker, and never stored
- [x] The adapter opens a pull request with its branch and files, reads a folder, reads a pull
      request's state and merges, tested against recorded shapes for every typed failure
- [x] Opening the same fix twice returns the first pull request; `pyjwt` is admitted through
      `make dep-check`; `make first-contact` mints a token and lists the installation's
      repositories, reading only

**Delivered 2026-10-15.** `finops_providers/github/app.py` signs a token naming the app with its
key for each request, asks GitHub which installation holds the repository, and exchanges it for an
installation token narrowed to that repository and to what the request needs; nothing keeps it,
and no detail carries it. The installation is found rather than stored, so TASK-P15-003's
connection needs no installation id; spec section 6 says so now. `finops_providers/github/code_host.py`
implements the four ports: a fix opens as one commit carrying `Meter-Reference`, an open pull
request is returned rather than a second opened, and an existing branch is moved only when its last
commit is Meter's for the same fix. GitHub's `mergeable_state` becomes the rule's readiness, and a
merge is GitHub's own at the head Meter read. `CodeHostKeyReader` reads the key from
`meter/<env>/codehost/`, which the hub task role may read and no wider. `pyjwt` was admitted
through `make dep-check` with zero findings. `make first-contact` lists the installation's
repositories with a token that may read metadata alone, and `docs/runbooks/code-host.md` has the
owner's steps. Tests in `tests/providers/github/` against shapes trimmed from GitHub's reference;
both modules at 100 percent coverage, measured. Unproved against a real installation, ISS-300.

---

### TASK-P15-003: the connection and the repository mapping

| Field | Value |
| --- | --- |
| Status | Done 2026-10-15 |
| Implements | Spec sections 5.1, 5.3, 6 and 8, OPEN-42 |
| Delivers | FEAT-091 |
| Depends on | TASK-P15-002 |
| Estimate | M |

**Acceptance criteria.**

- [x] A migration creates `code_host_connection` and `repository_mapping`, a check holding the key's
      name to the code host path
- [x] `GET` and `PUT /v1/remediation/connection` and `/repositories`, a change needing a person whose
      scope is the organization, audited ALLOWED or DENIED
- [x] An erasure keeps both and replaces the person's name on them

**Delivered 2026-10-15.** Migration `0059_code_host` creates `code_host_connection`, the app's id
and its key's secret name with a check holding the name to a code host path, and
`repository_mapping`, keyed by the state reference FEAT-057 records, with checks on the
repository's form, the branch and a folder that never climbs out of the repository. Both are
`PayerWide`. `finops_api/routes/remediation.py` answers `GET` and `PUT /v1/remediation/connection`
and `/repositories`: a narrowed reader is told why with a 404, a change needs a person whose scope
is the organization and is audited ALLOWED or DENIED, a key outside this environment's code host
path is refused, and the mapping is set whole, an unchanged state keeping who set it. The GET names
the states read with no mapping. No installation id is stored, TASK-P15-002. `erase_principal`
keeps both and replaces the name. Tests in `tests/api/test_remediation_routes.py` and the erasure
test in `tests/ingest/collectors/test_retention.py`.

---

### TASK-P15-004: a fix asked for, and a removal opened

| Field | Value |
| --- | --- |
| Status | Done 2026-10-15 |
| Implements | Spec sections 5.5, 6 and 7 |
| Delivers | FEAT-040, FEAT-092 |
| Depends on | TASK-P15-003 |
| Estimate | M |

**Acceptance criteria.**

- [x] A migration creates `fix_pull_request` and `fix_pull_request_event`, one live pull request per
      recommendation, and installs the `fix_pull_requests` cadence, every ten minutes
- [x] `POST /v1/waste/recommendations/{id}/pull-request` records the ask for a person whose scope
      includes the account; the collector opens a removal in the mapped repository, or records why
      it cannot, and the recommendation moves to `IN_PROGRESS`
- [x] The collector is scheduled, composed in both modes, and has a fake GitHub for the local stack

**Delivered 2026-10-15.** Migration `0060_fix_pull_request` creates the fix and its steps, one live
fix per recommendation held by a partial unique index, and installs the `fix_pull_requests` cadence
for every tenant. `POST /v1/waste/recommendations/{id}/pull-request`, in
`finops_api/routes/remediation.py`, records the ask for a person whose scope includes the account,
once the recommendation is accepted, audited. `finops_ingest/collectors/fix_pull_requests.py` opens
each requested fix through `propose`, each in its own savepoint: opened moves the recommendation to
IN_PROGRESS; nowhere to go is NOT_AUTHORED with the sentence why; a refusal the host will repeat is
FAILED with its cause; a throttled or silent host leaves the fix requested and ends the run.
`finops_ingest/codehost_bindings.py` builds it on the GitHub adapter, and the local stack on one fake
code host for the worker's life. It closed ISS-228, `propose` having had no caller.

---

### TASK-P15-005: gp2 to gp3 as an edit

| Field | Value |
| --- | --- |
| Status | Done 2026-10-15 |
| Implements | Spec section 5.4, OPEN-43 |
| Delivers | FEAT-093 |
| Depends on | TASK-P15-004 |
| Estimate | M |

**Acceptance criteria.**

- [x] `finops_query` edits the one block that declares the volume: the type to gp3, and IOPS and
      throughput where FEAT-074's rule needs more than gp3 includes, pure and tested on real
      Terraform text
- [x] It refuses, with the reason, a type set by a variable or an expression, a module's resource,
      an instance key, a block in no file or in several, and a volume gp3 cannot match
- [x] The collector reads the mapped folder and opens the edit as it opens a removal

**Delivered 2026-10-15.** `finops_query/gp3_edit.py` edits the one `aws_ebs_volume` block that
declares the volume: `type` to gp3, and `iops` and `throughput` where the priced gp3 gives more
than gp3 includes, with strings, comments and heredocs skipped when reading and an added line
aligned as `terraform fmt` aligns its run where the file already was. Every refusal the spec names
is a `NotAuthored` with its sentence. The figures it needs were only in the rationale, so migration
0061 keeps them on the recommendation, `target_iops` and `target_throughput_mibps`, held to the gp2
to gp3 class by a check, and the volume pass writes them. The `fix_pull_requests` collector reads
the mapped folder through the code host and opens the edit as it opens a removal. Tests in
`tests/query/test_gp3_edit.py` on Terraform text, 95 percent of the module, measured, and in the
collector's suite.

---

### TASK-P15-006: each pull request followed until the inventory sees it

| Field | Value |
| --- | --- |
| Status | Done 2026-10-15 |
| Implements | Spec section 5.6 |
| Delivers | FEAT-092 |
| Depends on | TASK-P15-005 |
| Estimate | M |

**Acceptance criteria.**

- [x] Each run reads every open pull request's state and records a merge or a close, with whom
- [x] A close without a merge returns the recommendation to `ACCEPTED`; a merge leaves it
      `IN_PROGRESS` until the inventory sees the change, then `DONE`, so FEAT-029 verifies it
- [x] `GET /v1/remediation/pull-requests` returns every fix asked for, its status and its steps

**Delivered 2026-10-15.** Each run of `fix_pull_requests` reads every open pull request's state:
merged is recorded with the host's login and `merged_at`, closed without merging with `closed_at`,
returning the recommendation to ACCEPTED, which the domain now allows from IN_PROGRESS, and a pull
request the host no longer knows is FAILED with its cause. A merged fix's recommendation is DONE
once a reading taken after the merge shows the change: the inventory lists the resource no more for
a removal, and `volume_observation`, which migration 0062 adds and the volume pass now restates for
every volume it reads, says gp3 for an edit. Nothing kept a volume's type before. `GET
/v1/remediation/pull-requests` lists every fix in the reader's scope with its steps.

---

### TASK-P15-007: the merge policy and Meter's merge

| Field | Value |
| --- | --- |
| Status | Done 2026-10-15 |
| Implements | Spec section 5.2, OPEN-41, ADR-0038 |
| Delivers | FEAT-094 |
| Depends on | TASK-P15-006 |
| Estimate | M |

**Acceptance criteria.**

- [x] A migration creates `merge_policy`, a check holding each class to the reversible set
- [x] `GET` and `PUT /v1/remediation/merge-policy`, with a reason, by a person whose scope is the
      organization, audited
- [x] The collector merges a pull request Meter opened, of a class the policy names, only when GitHub
      reports it mergeable with checks passed and reviews given, records the step, and merges
      nothing with the `pull_request_merge` flag off

**Delivered 2026-10-15.** Migration `0063_merge_policy` creates the policy, empty for every
tenant, with a check holding each class to the reversible set, and a test holds the check's list
equal to the domain's. `GET` and `PUT /v1/remediation/merge-policy` show and set it, with a reason,
for a person whose scope is the organization, audited, and refuse any class outside the set by
name. The `fix_pull_requests` collector merges an open pull request of a class the policy names
through `merge_under_policy` once GitHub reports it ready, records the merge as Meter's step with
the policy's sentence, and records a refusal once while GitHub repeats it. The `pull_request_merge`
flag is in the settings, `.env.example`, both tfvars maps and the register, and a run without
settings merges nothing. The fake code host merges too, at the head it reported, so the local
stack can.

---

### TASK-P15-008: the screens

| Field | Value |
| --- | --- |
| Status | Done 2026-10-15 |
| Implements | Spec section 8 |
| Delivers | FEAT-091, FEAT-092, FEAT-094 |
| Depends on | TASK-P15-007 |
| Estimate | M |

**Acceptance criteria.**

- [x] A recommendation's detail page lets a person ask for a fix, shows its pull request and its
      steps, and says why where there is none
- [x] A settings screen shows and changes the connection, the mapping and the merge policy for a
      person whose scope is the organization, and says why to anyone else
- [x] Unit tests and a Playwright journey

**Delivered 2026-10-15.** A recommendation's detail on the recommendations screen gains
`RecommendationFix`: an accepted recommendation's fix is asked for with an optional note, its pull
request is linked with every step, a fix with none says why, and a recommendation not yet accepted
says to accept it first. `/platform/fixes`, `FixSettingsScreen`, shows and changes the connection,
the mapping, through `DataTable`, and the merge policy for a person whose scope is the organization,
names the states with no mapping, says when merging is off, and tells anyone else why. The hooks are
`finops-web/src/api/remediation.ts`, plain queries since none of these routes exports, and the API
client gains `put`. Unit tests in `RecommendationFix.test.tsx` and `FixSettingsScreen.test.tsx`,
and a Playwright journey, `e2e/fixes.spec.ts`; the demo estate stubs the four routes.

---

### TASK-P15-009: the local stack, first contact, proof and documents

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 13 |
| Delivers | The exit criteria, measured, and the record |
| Depends on | TASK-P15-001 to TASK-P15-008 |
| Estimate | M |

**Acceptance criteria.**

- [ ] The seeded demo and the local stack carry a connection, a mapping and fixes in every status,
      against the fake GitHub
- [ ] `make first-contact` reads the app's installation, and a runbook names the owner's steps
- [ ] Every exit criterion in spec section 13 met, each with its evidence
- [ ] FEAT-040 and FEAT-091 to FEAT-094 say what was built; the register, `project_map.md` and the
      checkpoint updated, and `make check-docs` clean
