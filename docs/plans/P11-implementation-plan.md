# P11 Owners and a savings ledger: implementation plan

Date: 2026-10-08
Status: Approved by the owner on 2026-10-08 with OPEN-25 to OPEN-27 as recommended, in build. Chosen as the next priority, proposal 3 of `next-in-scope.txt`, OPEN-20
Spec: `docs/specs/2026-10-08-p11-owners-and-savings-ledger-design.md`
Depends on: P3 and P4 delivered. Proof against a real estate waits on ISS-002
Tasks: 9

An unowned finding is never fixed, and a fixed one earns its fixer nothing. This sub project reads
the owners an estate already names, from its tags, AWS's service catalogue and CloudTrail, shows
them beside every recommendation's assigned owner, and credits each verified saving to its owner
and team for every month the bill shows it held.

## How to work this plan

Same contract as P0 through P10. One task, one commit, `make verify` green before a merge.

**Four rules specific to P11.**

1. **A suggestion is never an owner.** No source writes `recommendation.owner`; a person does,
   spec section 5.1.
2. **Every owner says where it came from.** A source, a detail and `as_of`, or it is not shown.
3. **The ledger holds only what the bill shows.** A credit is a VERIFIED saving, and its months
   are measured; nothing is projected, and an unobserved month is never a zero, spec section 5.5.
4. **Teams, not people, are ranked**, spec section 5.6, until the owner answers OPEN-27 otherwise.

## Wave overview

| Wave | Tasks | Delivers | Can start when |
| --- | --- | --- | --- |
| A. The ports | 001 | Owner sources as ports, fakes with the planted cases | This plan approved |
| B. The sources | 002, 003, 004 | Tags, AppRegistry and CloudTrail creators in `resource_owner` | A |
| C. On the finding | 005 | Suggestions with their sources on every recommendation | B |
| D. The ledger | 006, 007, 008 | Credits, months held, routes and the screen | C for 006 |
| E. Proof and documents | 009 | Exit criteria measured and the documents | All |

Modelled at the pace of P9: eight tasks of size M and one of size S, about eight and a half working
days.

---

### TASK-P11-001: owner sources as ports, and the fake estate's owners

| Field | Value |
| --- | --- |
| Status | Done 2026-10-08 |
| Implements | Spec sections 5.1 to 5.4 |
| Delivers | `finops_core` types and ports, `finops_fakes` |
| Depends on | This plan approved |
| Estimate | M |

**Acceptance criteria.**

- [x] `OwnerSuggestion`, its source and kind, and the order of section 5.1, in `finops_core`,
      with no cloud SDK, constraint 1
- [x] `ServiceCatalogue` and `ResourceCreators` ports, and fakes that plant: a resource tagged
      under a second key, one in an application with an owner, one created by a person, one by
      a pipeline's role, and one created before CloudTrail's window
- [x] Contract tests every fake and adapter is held to

---

### TASK-P11-002: owners from tags, and the `ownership` collector

| Field | Value |
| --- | --- |
| Status | Done 2026-10-08 |
| Implements | Spec sections 5.2, 6 and 7 |
| Delivers | FEAT-077 |
| Depends on | TASK-P11-001 |
| Estimate | M |

**Acceptance criteria.**

- [x] `owner_tag_keys` in `Settings`, defaulting to `team`, the first key carried naming the team
- [x] `resource_owner`, its migration, constraints and `ByAccount` guard entry
- [x] The `ownership` collector, daily, its schedule row and reason, writing TAG rows from the
      inventory's nodes with no AWS call, and replacing the last run's

---

### TASK-P11-003: owners from AWS AppRegistry

| Field | Value |
| --- | --- |
| Status | Done 2026-10-08 |
| Implements | Spec section 5.3, OPEN-25 |
| Delivers | FEAT-077 |
| Depends on | TASK-P11-002 |
| Estimate | M |

**Acceptance criteria.**

- [x] The adapter reads applications, the tags that mark their resources and the owner under
      `catalogue_owner_key`, paging every list, held to the botocore model's shapes. Amended:
      AppRegistry associates stacks and a tag value, not resources, spec section 5.3
- [x] CATALOGUE rows written by the collector; a refused or throttled account is typed in
      `sync_error` and the other sources' rows stand
- [x] The hub's path to the AppRegistry API, held by `tests/contract/test_network_paths.py`

---

### TASK-P11-004: creators from CloudTrail

| Field | Value |
| --- | --- |
| Status | Done 2026-10-08 |
| Implements | Spec section 5.4, OPEN-26 |
| Delivers | FEAT-077 |
| Depends on | TASK-P11-002 |
| Estimate | M |

**Acceptance criteria.**

- [x] `LookupEvents` by `ResourceName` for the creating event, with the documented window and
      rate cited and held
- [x] A role session named as automation with its role; a resource older than the window said to
      be, never guessed
- [x] Each resource looked up once: never again once it has a creator row or a "before the
      window" row

---

### TASK-P11-005: suggestions on every recommendation

| Field | Value |
| --- | --- |
| Status | Done 2026-10-08 |
| Implements | Spec sections 5.1 and 8 |
| Delivers | FEAT-077, the change to FEAT-028 |
| Depends on | TASK-P11-002 |
| Estimate | M |

**Acceptance criteria.**

- [x] Recommendations carry `owner_suggestions`, strongest first, each with its source, detail and
      `as_of`, read through `resource_owner`'s guard; `suggested_owner` kept
- [x] The recommendations screen lists them under the owner cell, with their sources
- [x] A test that no source and no route writes `recommendation.owner`

---

### TASK-P11-006: a credit for every verified saving

| Field | Value |
| --- | --- |
| Status | Done 2026-10-11 |
| Implements | Spec section 5.5 |
| Delivers | FEAT-078 |
| Depends on | TASK-P11-005 |
| Estimate | M |

**Acceptance criteria.**

- [x] `savings_credit`, its migration, constraints and guard entry
- [x] The `savings_ledger` collector, daily, its schedule row: one credit per VERIFIED saving, its
      owner at DONE, its team, who closed it and the verified monthly saving
- [x] An INCONCLUSIVE or REGRESSED verdict earns no credit

---

### TASK-P11-007: the months a saving held

| Field | Value |
| --- | --- |
| Status | Done 2026-10-11 |
| Implements | Spec section 5.5 |
| Delivers | FEAT-078 |
| Depends on | TASK-P11-006 |
| Estimate | M |

**Acceptance criteria.**

- [x] `savings_credit_month`, its migration and constraints: HELD with a saving above nought,
      REGRESSED, or UNOBSERVED with neither cost nor saving
- [x] Each closed month measured against the cost before the change at FEAT-029's daily rate
- [x] A regressed month stops the accrual and says so; an unobserved month is never a zero

---

### TASK-P11-008: the ledger's routes and screen

| Field | Value |
| --- | --- |
| Status | Done 2026-10-11 |
| Implements | Spec sections 5.6 and 8 |
| Delivers | FEAT-078 |
| Depends on | TASK-P11-007 |
| Estimate | M |

**Acceptance criteria.**

- [x] `GET /savings/ledger`, teams by the savings they hold, and `GET /savings/ledger/credits`,
      one team's credits with their months, both exportable and scoped by account
- [x] A Savings ledger screen under Optimize, figures labelled measured, no ranking of
      individuals, with a journey
- [x] A reader narrowed to one account sees only that account's credits

---

### TASK-P11-009: proof and documents

| Field | Value |
| --- | --- |
| Status | Done 2026-10-11 |
| Implements | Spec section 13 |
| Delivers | The exit criteria, measured, and the record |
| Depends on | TASK-P11-001 to TASK-P11-008 |
| Estimate | S |

**Acceptance criteria.**

- [x] Every exit criterion in spec section 13 met, each with its evidence, against the seeded demo
- [x] FEAT-077, FEAT-078 and FEAT-028 say what was built; ISS-021 updated; the register,
      `project_map.md` and the checkpoint updated, and `make check-docs` clean

**Delivered 2026-10-11.** The spec's section 13, each criterion with its evidence. The test
counts are measured, from the full gate on TASK-P11-006's branch on 2026-10-11: 4025 backend tests,
952 frontend unit tests and 66 journeys passing, coverage 96.73 percent. Every figure the criteria
name is measured from the seeded demo's bill or planted by the fakes; a real estate waits on
ISS-002.

1. Every source is read on its planted case, and a failing one is typed and stands alone:
   `tests/scripts/test_p11_exit_criteria.py`,
   `test_every_source_reads_its_planted_case_and_a_failing_one_stands_alone`, finds the catalogue's
   two owners, the tag under the second key and the two creators, a person and a pipeline, in the
   seeded estate, then runs the collector with the catalogue refused and the event history
   throttled and finds both typed in `sync_error` with no row lost. Per source,
   `tests/ingest/collectors/test_ownership.py` and the contract test. TASK-P11-002 to TASK-P11-004.
2. Every recommendation shows its suggestions with their sources, and none is ever written as an
   owner: `test_every_recommendation_lists_its_suggestions_and_none_becomes_an_owner` holds every
   recommendation on the wire to its rows strongest first, and only the seed's finished work
   carries an owner; `tests/contract/test_suggestions_never_owners.py` holds the source text to it.
   TASK-P11-005.
3. Every verified saving in the seeded demo has one credit naming an owner, a team where one is
   known, and who closed it: `test_every_verified_saving_has_one_credit_naming_its_owner_team_and_closer`.
   TASK-P11-006.
4. Every credit's months are HELD, REGRESSED or UNOBSERVED, measured, and none is a zero for a month
   nobody observed: `test_every_month_is_held_regressed_or_unobserved_and_none_unseen_is_a_zero`
   judges the demo a season ahead, so months close past the bill's last day and come out
   unobserved. TASK-P11-007, with spec section 5.5 as amended on 2026-10-11.
5. The ledger ranks teams, never individuals, within the reader's scope, and is exportable:
   `test_the_ledger_ranks_teams_never_people_within_scope_and_exports`, with
   `tests/api/test_ledger_routes.py` and `e2e/ledger.spec.ts`. TASK-P11-008.

Open after P11: ISS-021 for owners on query findings and anomalies, and ISS-267 and ISS-268, two
test order leaks found while proving this.
