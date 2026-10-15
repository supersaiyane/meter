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
| Status | Not started |
| Implements | Spec sections 5.1 and 9, OPEN-13 |
| Delivers | FEAT-040, FEAT-091 |
| Depends on | TASK-P15-001 |
| Estimate | M |

**Acceptance criteria.**

- [ ] A token is minted per request from the app's key, read from `meter/<env>/codehost/` only by
      the worker, and never stored
- [ ] The adapter opens a pull request with its branch and files, reads a folder, reads a pull
      request's state and merges, tested against recorded shapes for every typed failure
- [ ] Opening the same fix twice returns the first pull request; `pyjwt` is admitted through
      `make dep-check`; `make first-contact` mints a token and lists the installation's
      repositories, reading only

---

### TASK-P15-003: the connection and the repository mapping

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec sections 5.1, 5.3, 6 and 8, OPEN-42 |
| Delivers | FEAT-091 |
| Depends on | TASK-P15-002 |
| Estimate | M |

**Acceptance criteria.**

- [ ] A migration creates `code_host_connection` and `repository_mapping`, a check holding the key's
      name to the code host path
- [ ] `GET` and `PUT /v1/remediation/connection` and `/repositories`, a change needing a person whose
      scope is the organization, audited ALLOWED or DENIED
- [ ] An erasure keeps both and replaces the person's name on them

---

### TASK-P15-004: a fix asked for, and a removal opened

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec sections 5.5, 6 and 7 |
| Delivers | FEAT-040, FEAT-092 |
| Depends on | TASK-P15-003 |
| Estimate | M |

**Acceptance criteria.**

- [ ] A migration creates `fix_pull_request` and `fix_pull_request_event`, one live pull request per
      recommendation, and installs the `fix_pull_requests` cadence, every ten minutes
- [ ] `POST /v1/waste/recommendations/{id}/pull-request` records the ask for a person whose scope
      includes the account; the collector opens a removal in the mapped repository, or records why
      it cannot, and the recommendation moves to `IN_PROGRESS`
- [ ] The collector is scheduled, composed in both modes, and has a fake GitHub for the local stack

---

### TASK-P15-005: gp2 to gp3 as an edit

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 5.4, OPEN-43 |
| Delivers | FEAT-093 |
| Depends on | TASK-P15-004 |
| Estimate | M |

**Acceptance criteria.**

- [ ] `finops_query` edits the one block that declares the volume: the type to gp3, and IOPS and
      throughput where FEAT-074's rule needs more than gp3 includes, pure and tested on real
      Terraform text
- [ ] It refuses, with the reason, a type set by a variable or an expression, a module's resource,
      an instance key, a block in no file or in several, and a volume gp3 cannot match
- [ ] The collector reads the mapped folder and opens the edit as it opens a removal

---

### TASK-P15-006: each pull request followed until the inventory sees it

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 5.6 |
| Delivers | FEAT-092 |
| Depends on | TASK-P15-005 |
| Estimate | M |

**Acceptance criteria.**

- [ ] Each run reads every open pull request's state and records a merge or a close, with whom
- [ ] A close without a merge returns the recommendation to `ACCEPTED`; a merge leaves it
      `IN_PROGRESS` until the inventory sees the change, then `DONE`, so FEAT-029 verifies it
- [ ] `GET /v1/remediation/pull-requests` returns every fix asked for, its status and its steps

---

### TASK-P15-007: the merge policy and Meter's merge

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 5.2, OPEN-41, ADR-0038 |
| Delivers | FEAT-094 |
| Depends on | TASK-P15-006 |
| Estimate | M |

**Acceptance criteria.**

- [ ] A migration creates `merge_policy`, a check holding each class to the reversible set
- [ ] `GET` and `PUT /v1/remediation/merge-policy`, with a reason, by a person whose scope is the
      organization, audited
- [ ] The collector merges a pull request Meter opened, of a class the policy names, only when GitHub
      reports it mergeable with checks passed and reviews given, records the step, and merges
      nothing with the `pull_request_merge` flag off

---

### TASK-P15-008: the screens

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 8 |
| Delivers | FEAT-091, FEAT-092, FEAT-094 |
| Depends on | TASK-P15-007 |
| Estimate | M |

**Acceptance criteria.**

- [ ] A recommendation's detail page lets a person ask for a fix, shows its pull request and its
      steps, and says why where there is none
- [ ] A settings screen shows and changes the connection, the mapping and the merge policy for a
      person whose scope is the organization, and says why to anyone else
- [ ] Unit tests and a Playwright journey

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
