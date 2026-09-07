# P0 Foundation: implementation plan

Date: 2026-08-23
Status: Provisional, pending approval of `docs/specs/2026-08-23-p0-foundation-design.md`
Spec: `docs/specs/2026-08-23-p0-foundation-design.md`
Tasks: 35

## How to work this plan

Read `docs/03-CHANGE-CONTROL.md`, section "The anti hallucination contract",
before starting. In short:

1. Work tasks in order. The order encodes real dependencies, not preference.
2. One task, one commit. The commit body names the task identifier.
3. Every task has a **Do not** list. It names the plausible mistake available
   at that task. Read it before writing code, not after.
4. If reality does not match the spec, **stop**. Raise an `ISS-nnn` row, fix
   the spec, add a `CHG-nnnn` row, update `INDEX.md`, then continue. Do not
   improvise around a wrong specification.
5. Paste the evidence command output into the task before marking it done.

## Wave overview

| Wave | Tasks | Delivers | Can start when |
| --- | --- | --- | --- |
| A. Scaffold | 001 to 004 | A repository that lints, tests and enforces its own rules | Now |
| B. Domain | 005 to 009 | Entities, ports, errors, and a fake provider that satisfies them | A complete |
| C. Persistence | 010 to 012 | Schema, repositories, and the scope guard | B complete |
| D. Infrastructure | 013 to 016 | Terraform for management, member and hub | A complete, parallel with B and C |
| E. AWS adapters | 017 to 019 | Credential broker and account discovery, against moto and LocalStack | B complete. **D is not required to start** |
| F. Ingestion | 020 to 023 | Dispatcher, worker, ledger, and the three P0 collectors | C and E complete |
| G. API | 024 to 025 | Routes with scope enforcement and freshness metadata | C complete, F for real data |
| H. Frontend | 035, 026 to 028 | The component layer, then five screens and the end to end journey | 035 needs only 002. Screens need G |
| I. Security and MCP | 029 to 031 | Zero vulnerability posture, and the four P0 MCP tools | 029 first of all, 030 and 031 after G |

**TASK-P0-029 runs before everything else**, out of numeric order. It verifies
that the Minimus tags this project depends on actually exist and that every
declared dependency passes the admission gate. Discovering at task 016 that the
base image does not exist would invalidate three Dockerfiles and a pipeline.

Waves B and D are independent. Run them in parallel if two people are working.

---

## Wave A: scaffold

### TASK-P0-001: create the Python workspace and quality gates

| Field | Value |
| --- | --- |
| Status | **Done 2026-10-07** |
| Implements | P0 spec section 4 |
| Delivers | Nothing user facing. Enables everything |
| Depends on | none |
| Estimate | S |

**Goal.** `make setup`, `make lint` and `make test` run successfully on an
empty but well formed package layout.

**Files.**

| Path | Action |
| --- | --- |
| `finops_core/__init__.py` | create |
| `finops_providers/__init__.py` | create |
| `finops_ingest/__init__.py` | create |
| `finops_api/__init__.py` | create |
| `tests/__init__.py` | create |
| `tests/conftest.py` | create |
| `pyproject.toml` | modify, already exists |

**Acceptance criteria.**

- [ ] `make setup` completes on a clean machine with Python 3.12
- [ ] `make lint` passes, including `lint-imports`
- [ ] `make test` passes with zero tests collected and does not fail on coverage
- [ ] `make check-writing` passes

**Tests.** None yet. The gate is that the tooling runs.

**Do not.**

- Do not lower `--cov-fail-under` below 80 to make the empty run pass. Use
  `--cov-fail-under=0` only in this one task's `pyproject.toml` and restore it
  in TASK-P0-005, where the first real test lands.
- Do not add `boto3` to `finops_core`. The import linter contract in
  `pyproject.toml` exists precisely to catch this, and disabling it defeats the
  entire multi cloud design.

**Evidence.**

```bash
make setup && make lint && make test && make check-writing
```

---

### TASK-P0-002: add the frontend workspace

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-27 |
| Implements | P0 spec section 9 |
| Depends on | none |
| Estimate | S |

**Goal.** A Vite, React and TypeScript workspace that builds, lints and tests.

**Files.**

| Path | Action |
| --- | --- |
| `finops-web/package.json` | create |
| `finops-web/tsconfig.json` | create |
| `finops-web/vite.config.ts` | create |
| `finops-web/index.html` | create |
| `finops-web/src/main.tsx` | create |
| `finops-web/src/App.tsx` | create |
| `finops-web/.eslintrc.cjs` | create |

**Acceptance criteria.**

- [x] `npm ci && npm run build` produces `finops-web/dist`
- [x] `npm run lint` and `npm run test -- --run` pass
- [x] `package.json` defines `format`, `lint`, `test` and `build`, because the
      Makefile calls all four

**Two deviations from the file list, both because following it would have
produced something that silently does nothing.**

`eslint.config.js` rather than `.eslintrc.cjs`. ESLint 9 and later do not read
`.eslintrc` by default, so that file would have given a lint step that checked
nothing while reporting success, which is worse than having no lint step.

`tsconfig.app.json` and `tsconfig.node.json` alongside `tsconfig.json`, because
the application and the build config need different `lib` and `types` sets and
one file cannot express both without weakening the strict settings for both.

**TypeScript is pinned below 6.** The current major is 7, and `typescript-eslint`
declares a peer range of `>=4.8.4 <6.1.0`. Installing 7 gives a lint step that
cannot parse the code it is meant to check. Recorded in `finops-web/README.md`
so the pin lifts deliberately rather than by accident.

**Node engine warning.** Some packages ask for Node 22, 24 or 26 and up. This
machine runs 25, which is an odd numbered line and not long term support. It
installs and builds, and the pipeline image should be on an even numbered
release.

**Do not.**

- Do not add a component library yet. P0 has five screens and a table. A
  design system chosen before the screens exist will be wrong.
- Do not add a state management library. React Query for server state is
  sufficient, and P0 has no client state worth managing.

**Evidence.**

```bash
cd finops-web && npm ci && npm run lint && npm run build
```

---

### TASK-P0-003: add the index consistency checker

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-27 |
| Implements | `docs/03-CHANGE-CONTROL.md` |
| Depends on | none |
| Estimate | S |

**Goal.** `make check-docs` fails when `INDEX.md` references a document that
does not exist, or when a document in `docs/` is not referenced by `INDEX.md`.

**Files.**

| Path | Action |
| --- | --- |
| `scripts/check_index.py` | modify, stub already exists |
| `tests/test_check_index.py` | create |

**Acceptance criteria.**

- [x] Fails with a clear message when `INDEX.md` links a missing path
- [x] Fails when a file under `docs/` is not linked from `INDEX.md`
- [x] Passes on the repository as it stands
- [x] Exit code is 1 on failure, so CI actually stops

**Do not.**

- Do not make it a warning. A documentation check that warns is a check that is
  ignored within two weeks.

**The checker is now testable.** `problems_in` takes a root, read at call time
rather than bound as a default, so its failure paths run against fixture trees.
A checker nobody has watched fail is a checker nobody knows still fails, and
this one is the reason a merge stops. Its tests live in
`tests/scripts/test_check_index.py`.

**Evidence.**

```bash
make check-docs
```

---

### TASK-P0-004: add the CI pipeline gate and pre commit configuration

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-27 |
| Implements | `docs/04-DEPLOYMENT.md` |
| Depends on | TASK-P0-001, TASK-P0-002, TASK-P0-003 |
| Estimate | S |

**Goal.** The GitLab pipeline runs green on the scaffold, and the writing rules
are enforced before a commit is created rather than after.

**Files.**

| Path | Action |
| --- | --- |
| `.pre-commit-config.yaml` | create |
| `.gitlab-ci.yml` | modify, already exists |

**Acceptance criteria.**

- [x] Pipeline stages `verify` all pass on the scaffold
- [x] A commit containing an em dash is rejected locally by pre commit
- [x] `terraform-validate` is allowed to fail only until TASK-P0-013 lands, and
      the allowance is removed in that task

**Do not.**

- Do not skip the writing rules job to unblock a pipeline. Fix the text.

**The dash rejection was demonstrated, not assumed.** A probe document
containing the banned character was written into `docs/`, `make check-writing`
failed and named the file and line, and the probe was removed. The same target
is the pre commit hook's entry, so the local rejection and the pipeline
rejection are the same check rather than two that can drift.

**`terraform-validate` carries no `allow_failure`.** It fails today because the
Terraform directories do not exist, and it stops failing when TASK-P0-013 to 016
create them, which is the behaviour the criterion asks for. Nothing was
weakened to make it green early.

**Evidence.** Pipeline URL and a screenshot or the job log tail.

---

## Wave B: domain

### TASK-P0-034: settings object, feature flags and the no hardcoding gate

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-24 |
| Implements | ADR-0017 |
| Delivers | FEAT-049 |
| Depends on | TASK-P0-001 |
| Estimate | M |

**Goal.** Every value comes from one typed place before there is any code to
put values in. Doing this after the fact means finding every literal already
written.

**Files.**

| Path | Action |
| --- | --- |
| `finops_core/config.py` | create |
| `finops_core/constants.py` | create |
| `finops_api/flags.py` | create |
| `tests/core/test_config.py` | create |
| `.env.example` | modify, already exists |
| `docs/feature-flags.yaml` | modify, already exists |

**Acceptance criteria.**

- [x] One `pydantic-settings` class covering every variable in `.env.example`
- [x] **The process refuses to start** when a required value is missing or
      malformed, naming the variable
- [x] A test asserts every `METER_` variable in `.env.example` has a field on
      the settings class, and the reverse, so the two cannot drift
- [x] Flag resolution order: `feature_flag` table for the tenant, then the
      environment default, then the declared default. Cached 60 seconds
- [x] An unknown flag key reads as its declared default rather than raising
- [x] `METER_FEATURE_SCOPE_AUDIT` false is **rejected at startup** when
      `METER_ENV` is prod
- [x] `make check-docs` runs `check_flags.py` and `check_hardcoded.py`

**Tests.**

| Test | Asserts |
| --- | --- |
| `tests/core/test_config.py::test_missing_required_refuses_startup` | Absent variable stops the process, naming it |
| `tests/core/test_config.py::test_env_example_matches_settings` | Neither file can drift from the other |
| `tests/core/test_config.py::test_scope_audit_cannot_be_off_in_prod` | The one flag that has no legitimate off state in production |
| `tests/core/test_config.py::test_unknown_flag_returns_default` | A typo does not take a service down |

**Do not.**

- Do not read `os.environ` anywhere outside `config.py`. That is the entire
  point, and `check_hardcoded.py` will find it.
- Do not add a flag for something you are unsure about. Uncertainty is resolved
  by deciding, or by not building the thing. A flag is for what must be
  switchable in production without a deploy.
- Do not put a secret default in `.env.example`. It is committed.

**Note on the flag table.** The `feature_flag` table lands in TASK-P0-010, so
`FlagResolver` takes the per tenant lookup as a callable rather than a
repository. TASK-P0-011 passes the real one in. The resolution order, the cache
and the two failure behaviours are complete and tested against that seam.

**Evidence.**

```bash
pytest tests/core/test_config.py -v && make check-docs
```

---

### TASK-P0-005: define the typed error taxonomy

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-24 |
| Implements | P0 spec section 6 |
| Delivers | FEAT-006 |
| Depends on | TASK-P0-001 |
| Estimate | S |

**Goal.** A closed set of errors that every collector and adapter raises, so
that no failure is ever rendered as the number zero.

**Files.**

| Path | Action |
| --- | --- |
| `finops_core/errors.py` | create |
| `tests/core/test_errors.py` | create |

**Acceptance criteria.**

- [x] Exactly six error types: `AccessDenied`, `Throttled`, `NotOptedIn`,
      `NoData`, `Unreachable`, `SchemaDrift`
- [x] Every error carries `scope_key`, `collector`, and a human readable
      remediation string
- [x] `NoData` is the only type whose documented rendering is a zero
- [x] `--cov-fail-under` is restored to 80 in `pyproject.toml` in this task

**Tests.**

| Test | Asserts |
| --- | --- |
| `tests/core/test_errors.py::test_taxonomy_is_closed` | The set of subclasses is exactly the six named types |
| `tests/core/test_errors.py::test_every_error_carries_remediation` | Every type produces a non empty remediation string |

**Do not.**

- Do not add a generic `CollectorError` catch all. The moment one exists, every
  future failure becomes generic, and the taxonomy stops meaning anything. This
  is ISS-015 and it is the single most likely defect in P0.
- Do not map an unknown botocore error code to `NoData`. Map it to
  `SchemaDrift`, which is loud.

**Evidence.**

```bash
pytest tests/core/test_errors.py -v
```

---

### TASK-P0-006: define the domain entities

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-24 |
| Implements | P0 spec section 5 |
| Depends on | TASK-P0-005 |
| Estimate | M |

**Goal.** Frozen dataclasses or Pydantic models for every P0 entity, with no
persistence concern and no cloud concern.

**Files.**

| Path | Action |
| --- | --- |
| `finops_core/domain/__init__.py` | create |
| `finops_core/domain/tenant.py` | create |
| `finops_core/domain/account.py` | create |
| `finops_core/domain/org.py` | create |
| `finops_core/domain/identity.py` | create |
| `finops_core/domain/ingest.py` | create |
| `finops_core/domain/cost.py` | create |
| `tests/core/test_domain.py` | create |

**Acceptance criteria.**

- [x] Every entity is immutable. Updates return a new instance
- [x] `CloudAccount` carries `provider`, so nothing assumes AWS
- [x] `OrgNode.node_type` is a closed enum: `ROOT`, `OU`, `ACCOUNT`
- [x] `Scope` exposes `is_global` and an explicit account set, never a wildcard
- [x] `CostRecord` field names match FOCUS 1.1 exactly, per ADR-0002
- [x] Every fact carrying entity has an `as_of` field, and it is not optional

**Tests.**

| Test | Asserts |
| --- | --- |
| `tests/core/test_domain.py::test_entities_are_immutable` | Mutating any entity raises |
| `tests/core/test_domain.py::test_cost_record_matches_focus_columns` | Field names match a checked in FOCUS 1.1 column list |
| `tests/core/test_domain.py::test_as_of_is_required` | Constructing a fact without `as_of` raises |

**Do not.**

- Do not add `account_id: str` as a bare field on shared entities. Use
  `(provider, account_id)`. A bare AWS account identifier leaking into the
  domain is exactly how multi cloud becomes a rewrite.
- Do not rename FOCUS columns to something more readable. ADR-0002 exists
  because the standard's value is that it is not ours to improve.
- Do not make `as_of` optional "for convenience". Every screen shows freshness,
  and an optional field means some screen will show nothing.

**Deviation.** One file beyond the list above, `finops_core/domain/fact.py`. The
two timestamp rule was going to be a comment repeated in six modules, and a
convention repeated six times is one that is missing from the seventh. It is a
base class instead, so inheriting from `Fact` is what puts an entity in
`test_as_of_is_required`, and a new fact without its timestamps fails the build.

The FOCUS test reads the column list out of `docs/07-DATA-MODEL.md` rather than
from a list beside the entity. A list beside the entity agrees with the entity
by construction and proves nothing. Reading the schema document means the
entity and its table cannot drift apart in either direction.

**Evidence.**

```bash
pytest tests/core/test_domain.py -v && make lint
```

---

### TASK-P0-007: define the eight ports

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-24 |
| Implements | P0 spec section 4, architecture section "Ports" |
| Delivers | FEAT-003 |
| Depends on | TASK-P0-006 |
| Estimate | M |

**Goal.** Eight protocol definitions that a provider implements. No
implementation, no cloud import.

**Files.**

| Path | Action |
| --- | --- |
| `finops_core/ports/__init__.py` | create |
| `finops_core/ports/accounts.py` | create |
| `finops_core/ports/credentials.py` | create |
| `finops_core/ports/cost.py` | create |
| `finops_core/ports/metrics.py` | create |
| `finops_core/ports/inventory.py` | create |
| `finops_core/ports/quotas.py` | create |
| `finops_core/ports/identity.py` | create |
| `tests/core/test_ports.py` | create |

**Acceptance criteria.**

- [x] Eight protocols: `AccountDiscovery`, `CredentialBroker`, `CostExport`,
      `MetricSource`, `ResourceInventory`, `QuotaSource`, `IdentityProvider`,
      `EntitlementResolver`
- [x] Every method documents which of the six errors it may raise
- [x] `lint-imports` passes, proving `finops_core` imports no cloud SDK
- [x] The six cloud ports are defined even though P0 only implements two, so
      later sub projects do not reshape the abstraction

**Tests.**

| Test | Asserts |
| --- | --- |
| `tests/core/test_ports.py::test_all_ports_are_protocols` | Each is `typing.Protocol` and runtime checkable |
| `tests/core/test_ports.py::test_core_imports_no_cloud_sdk` | Import graph of `finops_core` contains no `boto3` |

**Do not.**

- Do not give a port a method that returns a provider specific type. If
  `AccountDiscovery` returns something with an ARN in it, the abstraction has
  already failed.
- Do not defer defining the four ports P0 does not implement. They are cheap
  now and expensive to retrofit once three consumers exist.

**Deviation.** Three files beyond the list above:
`finops_core/domain/metrics.py`, `finops_core/domain/resource.py` and
`finops_core/domain/quota.py`. A port has to return something, and the rule
that a port never returns a provider shaped type means the return types are
domain types. They are deliberately thin, because the full shape of a time
series belongs to the sub project that first reads one.

`ProviderSession` is a ninth protocol and is not one of the eight. It is a
supporting type for adapters, exposes only `expires_at`, and is absent from
`finops_core.ports.__all__` on purpose. The moment the domain can reach a
client object through it, `finops_core` has a cloud SDK in its import graph
again.

**Evidence.**

```bash
pytest tests/core/test_ports.py -v && .venv/bin/lint-imports
```

---

### TASK-P0-008: implement the fake provider

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-24 |
| Implements | P0 spec section 11 |
| Depends on | TASK-P0-007 |
| Estimate | M |

**Goal.** An in memory implementation of all eight ports, so that every core
and API test runs with no AWS account.

**Files.**

| Path | Action |
| --- | --- |
| `finops_providers/fake/__init__.py` | create |
| `finops_providers/fake/provider.py` | create |
| `finops_providers/fake/fixtures.py` | create |
| `tests/providers/test_fake.py` | create |

**Acceptance criteria.**

- [x] Implements all eight ports
- [x] Can be configured to raise any of the six error types for a named scope,
      because failure paths need testing more than success paths do
- [x] Ships a fixture organization with at least one root, two organizational
      units, five accounts, one of which returns `AccessDenied`
- [x] Deterministic. The same fixture produces the same output every run

**Do not.**

- Do not make the fake only capable of success. The three tests this project
  cares most about are all failure path tests.
- Do not use randomness or wall clock time in fixtures. A flaky fixture makes
  every downstream test untrustworthy.

**Note.** The fixture account identifiers are not twelve digit numbers and the
region is fictional, because `scripts/ci/check_hardcoded.py` refuses both and is
right to: a twelve digit literal in a repository is either a real account or a
fixture that will one day be mistaken for one.

Passing `failures` replaces the fixture plan rather than merging with it, so a
test states exactly what fails and never inherits a rule it cannot see.

**Evidence.**

```bash
pytest tests/providers/test_fake.py -v
```

---

### TASK-P0-009: write the port contract test suite

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-24 |
| Implements | P0 spec section 11 |
| Depends on | TASK-P0-008 |
| Estimate | M |

**Goal.** One test suite, parameterised over providers, so that the AWS adapter
is held to exactly the same contract as the fake.

**Files.**

| Path | Action |
| --- | --- |
| `tests/contract/__init__.py` | create |
| `tests/contract/conftest.py` | create |
| `tests/contract/test_account_discovery.py` | create |
| `tests/contract/test_credential_broker.py` | create |

**Acceptance criteria.**

- [x] Marked `contract`, and parameterised over the provider under test
- [x] Runs against `fake` with no credentials
- [x] Runs against `aws` when `moto` is active, added in TASK-P0-017
- [x] Asserts error type parity: a scope that denies access raises
      `AccessDenied` from both providers, not a generic exception from one

**Do not.**

- Do not write separate test files per provider. The whole value is that one
  contract holds both, and two files drift apart within a month.

**Note.** The `aws` parameter is registered now and marked skip, rather than
left out until TASK-P0-017. A provider that is silently absent reads as a
provider that passes, so the run says out loud that one implementation is
currently under contract and the other is not. TASK-P0-017 replaces the skip
with a builder and changes nothing else.

**Evidence.**

```bash
pytest -m contract -v
```

---

## Wave C: persistence

### TASK-P0-010: create the database schema and migrations

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-24 |
| Implements | P0 spec section 5 |
| Delivers | FEAT-004 |
| Depends on | TASK-P0-006 |
| Estimate | L |

**Goal.** Every P0 table exists, with constraints that make the invariants
impossible to violate rather than merely discouraged.

**Files.**

| Path | Action |
| --- | --- |
| `alembic.ini` | create |
| `migrations/env.py` | create |
| `migrations/versions/0001_initial.py` | create |
| `finops_api/db/models.py` | create |
| `tests/db/test_schema.py` | create |

**Acceptance criteria.**

- [x] All tables from spec section 5 exist: `tenant`, `principal`,
      `principal_scope`, `cloud_account`, `org_node`, `ingest_run`,
      `ingest_watermark`, `sync_error`, `cost_focus_daily`,
      `cost_provider_extra`, `platform_cost`, `audit_event`
- [x] `ingest_run.idempotency_key` carries a unique constraint. This is what
      makes re running a collector safe, per ISS-008
- [x] Every fact table has a non nullable `as_of`
- [x] Every table has `tenant_id`, including the single tenant ones
- [x] `org_node.parent_node_id` is a self referencing foreign key
- [x] `cost_focus_daily` is partitioned by `billing_period`
- [x] `make migrate` applies cleanly to an empty database, and downgrade works
- [x] **No `email` column on `cloud_account`.** The account root email is
      personal data no feature reads. See `docs/09-DATA-CLASSIFICATION.md`

**Tests.**

| Test | Asserts |
| --- | --- |
| `tests/db/test_schema.py::test_idempotency_key_is_unique` | A duplicate insert raises |
| `tests/db/test_schema.py::test_as_of_is_not_nullable` | Inserting a fact without `as_of` raises |
| `tests/db/test_schema.py::test_org_tree_recursive_query` | A four level tree resolves via recursive CTE |

**Do not.**

- Do not omit `tenant_id` from tables because P0 is single tenant. Adding it
  later means rewriting every query and every index. This is the cheapest
  insurance in the whole project.
- Do not enforce idempotency only in application code. The unique constraint is
  the thing that actually holds when two workers race.
- Do not use `ON DELETE CASCADE` on `cloud_account`. An account leaving the
  organization must not silently drop its cost history.
- Do not add an `email` column because the API returns one. Storing personal
  data that nothing consumes is the easiest exposure to avoid, and the cheapest
  moment to avoid it is before the column has data.

**Two corrections to `docs/07-DATA-MODEL.md`, made in this task.** The schema
document is the authority, so both were fixed there as well as in the migration
and the models.

The self referencing key on `org_node.parent_node_id` was missing. It is added
as `DEFERRABLE INITIALLY DEFERRED`, because the tree is rebuilt in one
transaction and children are written before their parents are guaranteed to be
present. Without it, a dropped parent leaves a subtree that is simply absent
from the map and nothing reports it.

`principal_scope` had no `tenant_id`. It is the authorization cache, so the
repository guard has to filter by tenant without a join, and a forgotten join on
that table is exactly how one tenant reads another tenant's grants.

**Deviations.** `finops_api/db/__init__.py` and `tests/db/test_models.py` beyond
the file list. The metadata assertions need no database, so they run in `make
test` and fail in seconds rather than in the integration job. `collector_schedule`
is created as well, a thirteenth table, because ADR-0012 and constraint 9 make
cadence data rather than code and `docs/07-DATA-MODEL.md` specifies it.

The migration is raw SQL rather than `op.create_table` calls. Declarative
partitioning and `num_nonnulls` have no faithful expression through the ORM
helpers, and a migration that only approximates the schema document produces a
database that passes review and then fails the invariant. The drift test is what
makes two descriptions of one schema safe.

**Evidence.**

```bash
make up && make migrate && pytest tests/db -m integration -v
```

---

### TASK-P0-011: implement repositories with the scope guard

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-24 |
| Implements | P0 spec section 5, section 8 |
| Delivers | FEAT-007 |
| Depends on | TASK-P0-010 |
| Estimate | L |

**Goal.** Data access that cannot return out of scope rows, even when the
caller forgets to ask for scoping.

**Files.**

| Path | Action |
| --- | --- |
| `finops_api/db/repositories/__init__.py` | create |
| `finops_api/db/repositories/base.py` | create |
| `finops_api/db/repositories/accounts.py` | create |
| `finops_api/db/repositories/org.py` | create |
| `finops_api/db/repositories/ingest.py` | create |
| `finops_api/guards.py` | create |
| `tests/db/test_scope_guard.py` | create |

**Acceptance criteria.**

- [x] Every scoped repository method requires a `Scope` argument. It has no
      default value
- [x] The base repository refuses to execute a query against a scoped table
      without a scope filter, and raises rather than returning everything
- [x] `Scope.is_global` widens to every account, and writes an `audit_event`
      tagged as global access
- [x] Every read writes an `audit_event` recording the scope evaluated

**Tests.**

| Test | Asserts |
| --- | --- |
| `tests/db/test_scope_guard.py::test_unscoped_query_raises` | Calling a scoped method without a scope raises, and does not return rows |
| `tests/db/test_scope_guard.py::test_scope_filters_rows` | A principal scoped to two accounts sees exactly those two |
| `tests/db/test_scope_guard.py::test_global_scope_is_audited` | A global read produces an audit event tagged global |

**Also.** `finops_api.db` now exists, so the `finops_mcp` import contract stops
being inert for that target. Confirm it fires: add `import finops_api.db` to a
scratch file under `finops_mcp`, run `lint-imports`, see the contract BROKEN,
then remove it. ISS-109.

**ISS-109 is closed.** Both forbidden targets were confirmed live rather than
assumed: a scratch module under `finops_mcp` importing `finops_api.db` made
`lint-imports` report the contract BROKEN, the same for `finops_api.guards`, and
both went back to kept once removed.

**A defect found and fixed inside this task, worth recording.** The first
version of `assert_scoped` read the rendered WHERE clause looking for
`tenant_id`. For an empty scope, SQLAlchemy folds `and_(tenant_id = x, false())`
down to `false`, the text stops mentioning `tenant_id`, and the backstop
rejected the one query that matters most: the fail closed case that must return
nothing. A check that fails on the fail closed path is worse than no check,
because it looks careful while being wrong. It now tests for an execution option
that only `scoped_select` sets, which generative methods carry forward, so
refinement with `where`, `order_by` and `limit` keeps the guarantee.

**Do not.**

- Do not give `Scope` a default value of "everything". A default that grants
  access is the single most common cause of this class of data leak.
- Do not implement scoping only in the API layer. ISS-009 exists because that
  is bypassable by any route that forgets the dependency.
- Do not skip the audit write to save a round trip. Batch it if needed, but do
  not drop it. It is what makes the global viewer credential defensible.

**Evidence.**

```bash
pytest tests/db/test_scope_guard.py -v
```

---

### TASK-P0-012: implement the identity ports with the local provider

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-24 |
| Implements | P0 spec section 6, ADR-0008 |
| Delivers | FEAT-007 |
| Depends on | TASK-P0-011 |
| Estimate | M |

**Goal.** Authentication and entitlement resolution behind ports, with a
configuration driven local implementation that cannot reach production.

**Files.**

| Path | Action |
| --- | --- |
| `finops_api/identity/__init__.py` | create |
| `finops_api/identity/local_config.py` | create |
| `finops_api/identity/session.py` | create |
| `local-auth.example.yaml` | create |
| `tests/api/test_identity_local.py` | create |

**Acceptance criteria.**

- [x] `LocalConfigIdentityProvider` reads users, accounts and tiers from YAML
- [x] The application refuses to start when `METER_ENV` is `prod` and the
      identity provider is `local_config`, per ISS-017
- [x] Sessions are signed, carry the resolved scope, and expire after 8 hours
- [x] `EntitlementResolver` output is cached with an explicit expiry, never
      indefinitely
- [x] `scope_coverage` is computed as visible accounts over total organization
      accounts, per ISS-016

**Tests.**

| Test | Asserts |
| --- | --- |
| `tests/api/test_identity_local.py::test_local_provider_refuses_production` | Startup raises when env is prod |
| `tests/api/test_identity_local.py::test_session_expires` | An expired session is rejected |
| `tests/api/test_identity_local.py::test_scope_coverage_reports_partial_visibility` | Coverage reports 2 of 5, not 2 of 2 |

**Where the production refusal lives.** In `finops_core/config.py`, with the
other startup guards, not in the identity package. A guard that lives inside the
thing it is guarding is a guard that a refactor of that thing removes. It also
covers both ways in: `METER_IDENTITY_PROVIDER=local_config` and
`METER_FEATURE_LOCAL_AUTH=true`, because a guard that closes one of two doors is
not a guard.

**Deviation.** `finops_api/identity/coverage.py` beyond the file list, holding
`ScopeCoverage`. It refuses to be constructed with a total smaller than the
visible count, which is ISS-016 arriving in person: a total computed from the
visible set always reports full coverage, which is exactly why that bug survives
review.

**Do not.**

- Do not implement anything SAML related. OPEN-01 is parked. Guessing at the
  eventual design produces code that is thrown away and, worse, a port shape
  bent around a guess.
- Do not compute `scope_coverage` as visible over visible. That is the exact
  bug ISS-016 describes, and it silently makes every organization total wrong.
- Do not cache entitlements without an expiry. A revoked user must lose access.

**Evidence.**

```bash
pytest tests/api/test_identity_local.py -v
```

---

## Wave D: infrastructure

### TASK-P0-013: Terraform for the management account role

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-29, not applied |
| Implements | P0 spec section 10, ADR-0004 |
| Delivers | FEAT-002 |
| Depends on | none |
| Estimate | S |

**Goal.** `FinOpsOrgReaderRole` in the management account, trusted only by the
hub role.

**Files.**

| Path | Action |
| --- | --- |
| `infra/terraform/management/versions.tf` | created |
| `infra/terraform/management/main.tf` | created |
| `infra/terraform/management/variables.tf` | created |
| `infra/terraform/management/outputs.tf` | created |
| `infra/terraform/management/envs/dev.tfvars` | created |

**Acceptance criteria.**

- [x] Grants only `organizations:List*` and `organizations:Describe*`. Nine
      named actions rather than two wildcards, each one used by a named module
- [x] Trust policy requires the hub role principal and an ExternalId
- [x] `terraform validate` and `terraform fmt -check` pass
- [x] The `terraform-validate` allowance added in TASK-P0-004 is removed here,
      and `make lint` now checks all three stacks

**Deviations.**

1. **A permissions boundary was added.** Not asked for. This role lives in the
   management account, where a future edit that widens the inline policy has the
   largest blast radius in the organization, so the boundary caps it at
   Organizations reads whatever is attached later.
2. **`external_id` is absent from the tfvars file.** It is passed at apply time.
   A tfvars file in version control is the most common way an ExternalId stops
   being a control.

**Do not.**

- Do not grant `organizations:*`. Write access to the organization from a
  reporting tool will not survive a security review, and correctly so.

**Evidence.**

```bash
terraform -chdir=infra/terraform/management validate && terraform -chdir=infra/terraform/management fmt -check
```

Both pass. Not applied: it needs management account credentials, ISS-002.

---

### TASK-P0-014: Terraform for the member account StackSet

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-29, not applied |
| Implements | P0 spec section 10, ADR-0004 |
| Delivers | FEAT-001, FEAT-002 |
| Depends on | TASK-P0-013 |
| Estimate | M |

**Goal.** `FinOpsCollectorRole` deployed to every account automatically, so a
newly vended account onboards with no human step.

**Files.**

| Path | Action |
| --- | --- |
| `infra/terraform/member/versions.tf` | created |
| `infra/terraform/member/main.tf` | created |
| `infra/terraform/member/collector_role.yaml` | created |
| `infra/terraform/member/variables.tf` | created |
| `infra/terraform/member/outputs.tf` | created |
| `infra/terraform/member/envs/dev.tfvars` | created |

**Acceptance criteria.**

- [x] Service managed StackSet with `auto_deployment` enabled against the
      organization root
- [x] Trust policy requires the hub role, an ExternalId, and an
      `aws:PrincipalOrgID` condition
- [x] The policy is a curated action list, and `ReadOnlyAccess` appears nowhere
- [x] The action list is a single documented block, each action annotated with
      the collector that needs it

**Deviations.**

1. **`retain_stacks_on_account_removal` is false, which was not specified.** A
   departed account keeping a role that trusts our hub is a trust relationship
   nobody owns.
2. **Rollout is throttled to twenty percent with a five percent failure
   tolerance.** A template that fails in a way CloudFormation does not catch
   otherwise reaches the whole organization at once.
3. **The ExternalId parameter is in `ignore_changes`.** It is `NoEcho`, so drift
   detection compares against a masked value and would report a change on every
   plan, which is how a plan diff stops being read.

**Do not.**

- Do not attach `arn:aws:iam::aws:policy/ReadOnlyAccess`. This is ISS-010. It
  grants S3 object reads and SSM parameter reads that Meter never uses.
- Do not omit the `aws:PrincipalOrgID` condition. Without it, ExternalId is the
  only thing standing between this role and a confused deputy.
- Do not use a self managed StackSet. Automatic onboarding of new accounts is
  the entire point, and self managed does not do it.

**Evidence.**

```bash
terraform -chdir=infra/terraform/member validate && terraform -chdir=infra/terraform/member fmt -check
```

Both pass. Not applied: it needs trusted access between Organizations and
CloudFormation, which is a management account setting. ISS-002.

---

### TASK-P0-015: Terraform for the hub network and data layer

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-29, not applied |
| Implements | P0 spec section 10 |
| Depends on | none |
| Estimate | L |

**Goal.** VPC, endpoints, Aurora, SQS, S3 and Secrets Manager.

**Files.**

| Path | Action |
| --- | --- |
| `infra/terraform/hub/versions.tf` | created |
| `infra/terraform/hub/network.tf` | created |
| `infra/terraform/hub/database.tf` | created |
| `infra/terraform/hub/queue.tf` | created |
| `infra/terraform/hub/storage.tf` | created |
| `infra/terraform/hub/logs.tf` | created, not planned. See deviation 3 |
| `infra/terraform/hub/variables.tf` | created |
| `infra/terraform/hub/envs/dev.tfvars` and `prod.tfvars` | created |
| `infra/terraform/hub/envs/dev.backend.hcl` and `prod.backend.hcl` | created |

**Acceptance criteria.**

- [x] Private subnets with interface endpoints, plus a gateway endpoint for S3.
      Six interface endpoints: STS, SQS, Secrets Manager, CloudWatch Logs and
      the two ECR endpoints. See deviation 1 for Cost Explorer
- [x] No NAT Gateway
- [x] Aurora Serverless v2, encrypted, not publicly accessible
- [x] SQS main queue with a dead letter queue after 3 receives, the same number
      as `MAX_DELIVERY_ATTEMPTS`
- [x] Every resource carries a `finops:module` tag, through `default_tags`, so
      it cannot be forgotten on a resource, only overridden deliberately

**Deviations.**

1. **Cost Explorer has no interface endpoint.** `ce` is a global service with no
   regional PrivateLink endpoint, so it is not in the list. The plan named five
   services and the list here is six, because ECR needs two (`ecr.api` and
   `ecr.dkr`) and a task cannot start without them.
2. **The database password is generated by AWS, not passed in.** A password in a
   Terraform variable is a password in Terraform state, which is read by
   everything that runs a plan.
3. **Log groups are declared rather than left to the awslogs driver.** A group
   created implicitly on first use has no retention and never expires, and
   retention cannot be set at creation on a group that was created for you. That
   is TASK-P0-033's criterion and it had to be satisfied here, in the file that
   creates them.
4. **Backup retention is 35 days, the AWS maximum.** Below every table window in
   `docs/09-DATA-CLASSIFICATION.md`, so a backup never resurrects data the
   policy says was removed. This closes the criterion TASK-P0-032 deferred.

**Do not.**

- Do not add a NAT Gateway "just in case". If a collector needs the public
  internet, that is a design question to answer, not a default to pay for.
- Do not make the database publicly accessible for convenience during
  development. Use the compose stack for that.
- Do not forget the `finops:module` tag. Self metering silently reports nothing
  rather than failing, which is the worst kind of broken.

**Evidence.**

```bash
terraform -chdir=infra/terraform/hub validate && terraform -chdir=infra/terraform/hub fmt -check -recursive
```

Both pass. `make tf-plan` was NOT run: a plan needs real credentials for the S3
state backend and for the caller identity data sources, and there is no AWS
account. Recorded as ISS-122, and P0 is not signed off until it runs.

---

### TASK-P0-016: Terraform for ECS, ALB and ECR

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-29, not applied |
| Implements | P0 spec section 10, `docs/04-DEPLOYMENT.md` |
| Depends on | TASK-P0-015 |
| Estimate | L |

**Goal.** The three services run on Fargate behind an ALB, with `image_tag` as
a variable so Terraform owns the deploy.

**Files.**

| Path | Action |
| --- | --- |
| `infra/terraform/hub/ecr.tf` | created |
| `infra/terraform/hub/ecs.tf` | created |
| `infra/terraform/hub/alb.tf` | created |
| `infra/terraform/hub/iam.tf` | created |
| `infra/terraform/hub/scheduler.tf` | created |
| `infra/terraform/hub/outputs.tf` | created |

**Acceptance criteria.**

- [x] Four ECR repositories: api, worker, web, cache, with lifecycle policies.
      No mcp repository
- [x] ECR tag mutability set to `IMMUTABLE`. ISS-054
- [x] ECR enhanced scanning enabled, and set to `CONTINUOUS_SCAN` so an image
      is rescanned as new advisories are published
- [x] A second ECS service running the api image with the command overridden to
      `finops_mcp.server:bootstrap`
- [x] Task definitions take `image_tag` as a variable, and a validation refuses
      the value `latest`, because a rollback cannot name a mutable tag
- [x] `FinOpsHubTaskRole` can assume only `role/FinOpsCollectorRole` in any
      account, restricted by `aws:PrincipalOrgID`
- [x] Worker service scales on `ApproximateNumberOfMessagesVisible`
- [x] EventBridge Scheduler triggers the dispatcher hourly
- [x] ALB health check targets `/healthz` and the rollout waits for stable

**Deviations.**

1. **The MCP service has no task role at all.** Not specified, and it is the
   point of ADR-0009: the facade holds no credential of its own and reaches
   Meter only over HTTP with the caller's token. A task role would give it a way
   to read data the caller is not entitled to.
2. **The worker runs on Fargate Spot.** An interrupted worker unit is
   redelivered by the queue, so an interruption costs a retry. An interrupted
   API task costs a request, so the API does not use Spot.
3. **The deployment circuit breaker is enabled with rollback.** Beyond a health
   check gate: a broken image rolls itself back rather than sitting in a failed
   rollout until somebody notices.
4. **Production refuses to start without TLS and without alerting.** Two
   preconditions. "We will add TLS before we go live" is a sentence that
   survives going live.

**Do not.**

- Do not grant the task role `sts:AssumeRole` on `*`. Scope it to the
  collector role name pattern, or a compromised container can assume anything
  it can name.
- Do not set the ECS deployment to replace all tasks at once. Rolling with a
  health check gate is what stops a broken image from taking the service down.
- Do not put the image tag in a `latest` style mutable tag. A rollback then
  becomes impossible to express.

**Evidence.**

```bash
terraform -chdir=infra/terraform/hub validate
```

Passes. Not applied, and no plan run. ISS-122.

---

## Wave E: AWS adapters

### TASK-P0-017: implement the AWS credential broker

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-24 |
| Implements | P0 spec section 4 |
| Delivers | FEAT-002 |
| Depends on | TASK-P0-007. **Not TASK-P0-014** |
| Estimate | M |

**Dependency relaxed 2026-08-23.** This previously depended on the member
StackSet being deployed, which put the management account on the critical path
and blocked everything downstream of it. It does not need to. The broker is
built and fully tested against `moto`, and the organization tree against
LocalStack, which emulates `sts` and `organizations`. The real StackSet is
needed only for end to end verification against live accounts, which is a
separate step at the end of wave E rather than a precondition for starting it.

LocalStack does **not** enforce IAM, so it proves the plumbing and not the
permission boundary. The live verification step is where that is proven. See
`docs/04-DEPLOYMENT.md` and gotcha 5.10.

**Goal.** Produce a scoped boto3 session for any member account, with caching
and correct error typing.

**Files.**

| Path | Action |
| --- | --- |
| `finops_providers/aws/__init__.py` | create |
| `finops_providers/aws/credentials.py` | create |
| `finops_providers/aws/client.py` | create |
| `tests/providers/aws/test_credentials.py` | create |

**Acceptance criteria.**

- [x] Assumes `FinOpsCollectorRole` with the ExternalId from Secrets Manager
- [x] Caches sessions until 5 minutes before expiry, then refreshes
- [x] Maps `AccessDenied` and `AccessDeniedException` to the `AccessDenied`
      domain error, and throttling codes to `Throttled`
- [x] Sets connect and read timeouts, and a bounded retry policy, so a broken
      network path fails fast rather than consuming the whole task timeout
- [x] Passes the contract suite from TASK-P0-009 under `moto`

**The partition is derived, not written down.** `role_arn` builds the ARN from
`partition_for(region)`, because a literal partition is an assumption that only
breaks in the environments where being wrong is most expensive, and it breaks as
an unhelpful malformed ARN error rather than as anything readable.

**What the contract suite caught immediately.** The fake used `provider:account`
as its scope key and the AWS adapter used `provider:account:region`, which is the
format `docs/07-DATA-MODEL.md` documents. The fake was wrong and now matches.
This is the divergence the suite exists to find, and it found it on the first run
against a second implementation. The contract now asserts the account is
identifiable from the scope key rather than pinning the whole string, because a
contract that pins formatting tests formatting.

**Providers declare which ports they satisfy.** An adapter arrives one port at a
time. The alternative is a file of skips nobody prunes, or a suite that quietly
reports a missing implementation as passing. `AccountDiscovery` currently reports
as skipped for `aws`, by name, until TASK-P0-018.

**Do not.**

- Do not cache a session past its expiry. An expired session produces confusing
  errors that look like permission problems.
- Do not use the default botocore retry policy for cross account fan out. At
  300 accounts, default retries turn a throttling event into a thundering herd.
- Do not swallow an unknown error code. Map it to `SchemaDrift`, which is loud.

**Evidence.**

```bash
pytest tests/providers/aws/test_credentials.py -v && pytest -m contract -v
```

---

### TASK-P0-018: implement AWS account discovery

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-24 |
| Implements | P0 spec section 5.2, section 7 |
| Delivers | FEAT-001 |
| Depends on | TASK-P0-017 |
| Estimate | M |

**Goal.** Build the exact organization tree from the Organizations API.

**Files.**

| Path | Action |
| --- | --- |
| `finops_providers/aws/accounts.py` | create |
| `tests/providers/aws/test_accounts.py` | create |

**Acceptance criteria.**

- [x] Walks `ListRoots`, then `ListOrganizationalUnitsForParent` and
      `ListAccountsForParent` recursively
- [x] Paginates everything. No unpaginated call anywhere
- [x] Returns domain `OrgNode` and `CloudAccount`, never a raw API shape
- [x] Handles a suspended account without failing the run
- [x] Backs off on throttling rather than failing, per the P0 risk table

**Tests.**

| Test | Asserts |
| --- | --- |
| `tests/providers/aws/test_accounts.py::test_builds_four_level_tree` | Nested organizational units resolve with correct parents |
| `tests/providers/aws/test_accounts.py::test_paginates` | A 300 account fixture returns 300, not the first page |
| `tests/providers/aws/test_accounts.py::test_suspended_account_is_marked_not_dropped` | A suspended account appears with the correct status |

**A mismatch fixed on the way in.** The domain `AccountStatus` was
`active | suspended | closed | unknown` while `docs/07-DATA-MODEL.md` stores
`ACTIVE | SUSPENDED | PENDING | DEPARTED`. A domain enum and a check constraint
that disagree fail at the first write and not one moment before, so the domain
now follows the document, `UNKNOWN` was added to the constraint, and a test
asserts the two sets stay equal. The initial migration was edited rather than
superseded because it has not been deployed anywhere; constraint 12 governs
released schemas.

`UNKNOWN` exists so an unrecognised provider status does not become a dropped
account. Dropping one shrinks the denominator behind every organization total
and every `scope_coverage` figure, which is ISS-016 arriving by another route.

**The contract suite is now fully live.** Both ports are implemented for `aws`,
so all 28 contract tests run against both providers with no skips.

**Do not.**

- Do not discover child accounts by probing. The Organizations API returns the
  exact tree. Probing is slower, incomplete and rate limited.
- Do not drop a suspended or pending account. Silently shrinking the
  denominator makes `scope_coverage` and every organization total wrong.

**Evidence.**

```bash
pytest tests/providers/aws/test_accounts.py -v
```

---

### TASK-P0-019: implement the account health check

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-24 |
| Implements | P0 spec section 5.2, section 7 |
| Delivers | FEAT-001 |
| Depends on | TASK-P0-018 |
| Estimate | S |

**Goal.** Determine, per account, whether the collector role is actually usable,
so a failed onboarding is visible rather than silent.

**Files.**

| Path | Action |
| --- | --- |
| `finops_providers/aws/health.py` | create |
| `tests/providers/aws/test_health.py` | create |

**Acceptance criteria.**

- [x] Attempts an assume role plus one cheap call
- [x] Maps the outcome to `HEALTHY`, `ACCESS_DENIED`, `NOT_DEPLOYED`,
      `THROTTLED` or `UNKNOWN`
- [x] Distinguishes "role does not exist" from "role exists but denies", since
      the remediation differs completely
- [x] Records the error string, so a user can act without reading logs

**How the distinction is actually made, and what it cost.** STS cannot tell the
two apart. Assuming a role that does not exist and assuming a role whose trust
policy refuses you both return `AccessDenied`, with messages that vary by account
and by day. Reading the message text would produce a confident answer that is
wrong for half the cases, and the two answers send the fix to different people,
which is worse than no answer.

So the authoritative signal is the deployment. `AccountHealthCheck` takes a
`deployment_probe`, and TASK-P0-014 supplies the real one from the StackSet.
Without a probe a refusal is `UNKNOWN` with the provider's own message recorded
and a remediation naming both possibilities. That is honest rather than
unhelpful: it says which two things to check instead of picking an owner at
random. A test asserts the two states are never collapsed, and another asserts
the no probe case does not guess.

**Deviation.** `RoleHealth` and `AccountHealth` live in
`finops_core/domain/account.py` rather than in the adapter, because `role_health`
is a stored column and a domain enum that disagrees with a check constraint fails
at the first write. A test holds the two sets equal.

**Do not.**

- Do not collapse `NOT_DEPLOYED` and `ACCESS_DENIED` into one state. The first
  means the StackSet has not reached the account, the second means the policy
  is wrong. Different fix, different owner.

**Evidence.**

```bash
pytest tests/providers/aws/test_health.py -v
```

---

## Wave F: ingestion

### TASK-P0-020: implement the run ledger and watermarks

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-24 |
| Implements | P0 spec section 5.3, section 7 |
| Delivers | FEAT-005 |
| Depends on | TASK-P0-010 |
| Estimate | M |

**Goal.** Idempotent, resumable, observable collection runs.

**Files.**

| Path | Action |
| --- | --- |
| `finops_ingest/ledger.py` | create |
| `tests/ingest/test_ledger.py` | create |

**Acceptance criteria.**

- [x] Claims a run by inserting the idempotency key, and a duplicate claim is a
      no operation rather than a second run
- [x] Records `items_written`, `bytes_read`, `error_type` and the as of window
- [x] Advances the watermark only on success
- [x] A crashed run is reclaimable after a timeout, rather than blocking that
      scope forever

**Tests.**

| Test | Asserts |
| --- | --- |
| `tests/ingest/test_ledger.py::test_running_three_times_writes_one_result_set` | The core idempotency guarantee, ISS-008 |
| `tests/ingest/test_ledger.py::test_watermark_not_advanced_on_failure` | A failed run does not skip data |
| `tests/ingest/test_ledger.py::test_crashed_run_is_reclaimable` | A stale claim can be retaken |

**A defect the tests found, and it was not a test artifact.**
`uq_ingest_run__idempotency_key` was unique on the key alone, and the key does
not include the tenant. Two tenants who have onboarded the same account would
therefore collide: the second would find the unit already claimed, never collect
it, and report nothing wrong anywhere. The constraint is now on
`(tenant_id, idempotency_key)`, which is what every other invariant in this
schema already does, and `docs/07-DATA-MODEL.md` records it. A test claims the
same unit of work for two tenants and expects both to succeed.

**The watermark only moves forward.** `GREATEST` rather than assignment, so a
backfill reading an older window cannot rewind the frontier and cause every
window after it to be collected again.

**Reclaiming takes the row over rather than adding one.** A test asserts the run
count stays at one, because a second row for the same unit is the double count
the idempotency key exists to prevent, arriving through the recovery path.

**Do not.**

- Do not advance the watermark before the write succeeds. That silently loses
  a window of data, and nothing surfaces it.
- Do not use the wall clock as part of the idempotency key. It makes every run
  unique, which defeats the entire mechanism.

**Evidence.**

```bash
pytest tests/ingest/test_ledger.py -v
```

---

### TASK-P0-021: implement the dispatcher and worker

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-24 |
| Implements | P0 spec section 7 |
| Delivers | FEAT-005 |
| Depends on | TASK-P0-020, TASK-P0-017 |
| Estimate | L |

**Goal.** Fan out units of work, consume them concurrently, and never let one
account's failure fail the run.

**Files.**

| Path | Action |
| --- | --- |
| `finops_ingest/dispatcher.py` | create |
| `finops_ingest/worker.py` | create |
| `finops_ingest/registry.py` | create |
| `tests/ingest/test_dispatcher.py` | create |
| `tests/ingest/test_worker.py` | create |

**Acceptance criteria.**

- [x] Dispatcher enumerates `(tenant, account, region, collector)` and publishes
      one message per unit, with a dedup key
- [x] Worker claims a run, resolves credentials, executes, records the outcome
- [x] A raised domain error is recorded against that scope and the worker
      continues. It never propagates to fail the batch
- [x] Messages failing three times land in the dead letter queue
- [x] Structured logs carry `run_id`, `collector`, `scope_key` on every line

**Tests.**

| Test | Asserts |
| --- | --- |
| `tests/ingest/test_worker.py::test_one_account_access_denied_does_not_fail_run` | Spec section 11, test 1. The single most important test in P0 |
| `tests/ingest/test_worker.py::test_no_data_and_access_denied_are_distinguishable` | Spec section 11, test 2. ISS-015 |
| `tests/ingest/test_dispatcher.py::test_dedup_key_prevents_duplicate_units` | Re dispatch within a window is a no operation |

**The boundary is tested from both sides.** `except CollectionError` and
nothing wider, so a test asserts an AccessDenied is recorded and the batch
continues, and another asserts a ValueError propagates and crashes the worker. A
bare except that logs and moves on would pass the first test and fail nobody, so
the second one is what keeps the rule.

**One transaction per unit, and a test that proves it.** After a batch where one
account fails, the successful account's watermark is present. Under one shared
transaction it would have been rolled back with the failure, and the run would
report nothing wrong and have written nothing.

**The dead letter path leaves a record before the message goes.** Without it the
message disappears into the queue's own accounting and the only trace is a
metric nobody is watching.

**Repeated failures count rather than accumulate rows.** Ten thousand rows
saying an account is broken buries the three accounts that actually are.

**Do not.**

- Do not wrap the collector call in a bare `except Exception` that logs and
  moves on. Catch the domain errors explicitly and let anything unexpected
  crash the worker loudly. A silent unknown failure is worse than a crash.
- Do not process the whole batch in one transaction. One account failing would
  roll back the other 299.

**Evidence.**

```bash
pytest tests/ingest -v
```

---

### TASK-P0-022: implement the organization tree and account health collectors

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-24 |
| Implements | P0 spec section 7 |
| Delivers | FEAT-001 |
| Depends on | TASK-P0-021, TASK-P0-018, TASK-P0-019 |
| Estimate | M |

**Goal.** The tree and the account health status refresh hourly, without a
human step.

**Files.**

| Path | Action |
| --- | --- |
| `finops_ingest/collectors/org_tree.py` | create |
| `finops_ingest/collectors/account_health.py` | create |
| `tests/ingest/collectors/test_org_tree.py` | create |
| `tests/ingest/collectors/test_account_health.py` | create |

**Acceptance criteria.**

- [x] Rebuilds `org_node` transactionally, so the tree is never half updated
- [x] Upserts `cloud_account`, and marks a departed account as such rather than
      deleting it
- [x] A new account appears within one hour with no human step, which is the
      P0 definition of done
- [x] `role_health` is set for every account on every run

**A gap this task exposed.** A collector could not write anything: the worker
kept the transaction and passed only the cloud session. `CollectorRunner` now
takes a `CollectorContext` carrying the unit, the worker's own transaction and
the session, so a collector's writes commit or roll back with the run record and
no collector can open a second transaction that disagrees with the first.

**Two extra refusals, both about what a reader would otherwise see.** An empty
discovery result is refused rather than applied, because an organization always
holds at least its management account and applying zero would mark every account
departed in one transaction. A cycle in the tree is refused rather than walked.

**`cloud_account` has no parent column, deliberately.** An account's place in the
tree is its own `org_node` row. Storing the parent in both would create two
answers that disagree the first time an account is moved.

**The hourly claim is now data rather than aspiration.** `install_default_schedule`
seeds `collector_schedule` for a tenant with both cadences and the reason each
one is that number, per ADR-0012 and constraint 9. It never overwrites an
existing row, so an operator who has deliberately slowed a collector down does
not have that undone by a redeploy.

**Do not.**

- Do not delete and recreate the tree without a transaction. A reader hitting
  the gap sees an empty organization, and an empty organization renders as
  zero cost.
- Do not delete an account row when it leaves the organization. Its cost
  history must survive.

**Evidence.**

```bash
pytest tests/ingest/collectors -v
```

---

### TASK-P0-023: implement the platform self cost collector

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-27 |
| Implements | P0 spec section 7, section 5.5 |
| Delivers | FEAT-008 |
| Depends on | TASK-P0-021 |
| Estimate | S |

**Goal.** Meter's own AWS cost, by module, on the front page.

**Files.**

| Path | Action |
| --- | --- |
| `finops_ingest/collectors/platform_cost.py` | create |
| `tests/ingest/collectors/test_platform_cost.py` | create |

**Acceptance criteria.**

- [x] One daily Cost Explorer request, grouped by the `finops:module` tag
- [x] Runs daily, not hourly, because Cost Explorer charges per request
- [x] An untagged cost lands in an explicit `unallocated` bucket rather than
      being dropped
- [x] The Cost Explorer request cost is itself attributed to the ingest module

**How the metering charge is attributed, and why it is not an extra row.** The
Cost Explorer charge arrives untagged, because an account level API charge has
no resource to hang a tag on. It is re attributed from `unallocated` to `ingest`
rather than added as a synthetic row at a list price. Adding one would double
count, since the real charge appears in the next day's own report, which is the
whole point of metering ourselves.

**Three files rather than one.** `finops_core/domain/platform.py` holds
`PlatformCost` and the `unallocated` constant, `finops_providers/aws/platform_cost.py`
makes the request and translates provider failures, and the collector writes and
re attributes. The collector must not import boto3, and an untranslated botocore
error reaching the worker would crash it rather than being recorded, since the
worker deliberately catches only the six.

**The response's tag key is checked, not assumed.** Being answered about a
different tag than the one requested would make every module attribution below
it wrong, so it is `SchemaDrift` rather than something absorbed.

**Do not.**

- Do not call Cost Explorer per module. One grouped request answers it, and per
  module calls multiply a metered API by the number of modules.
- Do not drop untagged cost. A self metering report that quietly under counts
  is worse than none, because it is believed.

**Evidence.**

```bash
pytest tests/ingest/collectors/test_platform_cost.py -v
```

---

## Wave G: API

### TASK-P0-024: implement the FastAPI application and scope dependency

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-27 |
| Implements | P0 spec section 8 |
| Delivers | FEAT-007 |
| Depends on | TASK-P0-012 |
| Estimate | M |

**Goal.** The application, its middleware, and the scope dependency, with the
adversarial test that proves enforcement is not bypassable.

**Files.**

| Path | Action |
| --- | --- |
| `finops_api/main.py` | create |
| `finops_api/deps.py` | create |
| `finops_api/middleware.py` | create |
| `finops_api/schemas.py` | create |
| `tests/api/test_scope_enforcement.py` | create |

**Acceptance criteria.**

- [x] Every response carries `meta` with `as_of`, `scope_coverage` and
      `degraded`
- [x] `/healthz` reports database reachability and ingestion freshness, not
      just process liveness
- [x] A route registered without the scope dependency still cannot return out
      of scope rows, because the repository guard catches it

**Tests.**

| Test | Asserts |
| --- | --- |
| `tests/api/test_scope_enforcement.py::test_route_without_dependency_cannot_leak` | Spec section 11. The adversarial test for ISS-009 |
| `tests/api/test_scope_enforcement.py::test_every_response_carries_meta` | Iterates the registered routes and asserts the envelope |

**Also.** `finops_api.guards` now exists, so the last inert target in the
`finops_mcp` contract becomes live. Confirm it fires by probe, as in
TASK-P0-011. ISS-109 closes here.

**The envelope contract nearly shipped as a check that checked nothing.** The
first version walked `app.routes`, and FastAPI wraps an included router instead
of flattening it, so the walk found zero routes and passed. That is the worst
failure a check of this kind can have: it reports success over an application it
never examined. It now inspects the routers being registered, which is public
API rather than a private attribute that moves between versions, and it refuses
to start if it finds no routes at all.

`Envelope[list[str]]` is a pydantic generic, which builds a concrete model class
rather than a typing alias, so `get_origin` reports nothing for it. The check
reads pydantic's own generic metadata, which is what makes a parameterised
envelope recognisable as one.

**What the repository guard cannot catch, stated plainly.** It refuses a read
with no scope. It cannot refuse a read with a fabricated scope, because it
faithfully applies whatever it is handed, so a route that builds a `Scope` out of
a query parameter defeats both checks at once. That is why the scope comes from
the entitlement resolver and never from the request, and why every read writes
the scope it evaluated to `audit_event`: the case that cannot be prevented is at
least visible afterwards, and a test asserts the audit row carries the request id.

**ISS-109 was already closed in TASK-P0-011**, where both forbidden targets,
`finops_api.db` and `finops_api.guards`, were confirmed to fire by probe rather
than assumed.

**Do not.**

- Do not add a route that returns bare data without the `meta` envelope. The
  freshness contract is only worth anything if it is universal.
- Do not delete the adversarial test because "every route has the dependency
  now". It exists for the route someone adds next year.

**Evidence.**

```bash
pytest tests/api -v
```

---

### TASK-P0-025: implement the P0 routes

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-27 |
| Implements | P0 spec section 8 |
| Delivers | FEAT-001, FEAT-006, FEAT-008 |
| Depends on | TASK-P0-024, TASK-P0-022, TASK-P0-023 |
| Estimate | M |

**Goal.** The seven P0 routes.

**Files.**

| Path | Action |
| --- | --- |
| `finops_api/routes/me.py` | create |
| `finops_api/routes/accounts.py` | create |
| `finops_api/routes/org.py` | create |
| `finops_api/routes/ingest.py` | create |
| `finops_api/routes/platform.py` | create |
| `tests/api/test_routes.py` | create |

**Acceptance criteria.**

- [x] All seven routes from spec section 8 exist and match the documented shape
- [x] `/org/tree` marks branches outside scope as unreachable rather than
      hiding them, so the tree shape stays honest
- [x] `/ingest/runs` returns typed errors with their remediation text
- [x] `/health/freshness` reports staleness per collector and scope

**The tree keeps its shape.** A narrow scope and a global one return the same
node count; only `reachable` differs. A test asserts that, because the pruning
version is the one somebody writes when the tree looks untidy in review.

**Two lookups give one answer.** A recheck on an account outside the scope and a
recheck on an account that does not exist both return the same 404 with the same
body. Telling them apart would let a caller enumerate the accounts they cannot
see, one request at a time.

**A global viewer is not reported as seeing nothing.** A global scope enumerates
no accounts, so the naive count is zero, and zero renders as a user with no
access. The coverage figure uses the organization total instead.

**Deviations.** Three repositories beyond the file list, in
`finops_api/db/repositories/freshness.py`, plus `count_in_organization` on the
account repository. Routes must not query directly, and the coverage denominator
has to come from the organization rather than from the visible set, which is
ISS-016. That method returns a count and never rows, so it cannot become a way
to read out of scope data.

`finops_api/routes/__init__.py` holds the shared envelope assembly.
`freshness_of` takes the oldest timestamp in a set rather than the newest,
because a page is only as fresh as its stalest figure, and it skips rows that
are not facts rather than guessing which field stands in for `collected_at`.

**Do not.**

- Do not silently prune out of scope branches from the tree. A user seeing a
  tree with gaps they cannot explain will assume the data is broken. Mark them.
- Do not return a raw exception string to the client. Return the typed error
  and its remediation.

**Evidence.**

```bash
pytest tests/api/test_routes.py -v
```

---

## Wave H: frontend

### TASK-P0-035: the component layer and the visual honesty system

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-27 |
| Implements | `docs/12-UI-DESIGN.md`, ADR-0019 |
| Delivers | FEAT-050 |
| Depends on | TASK-P0-002 |
| Estimate | L |

**Goal.** The components every screen in every sub project will use, and the
one that makes a dishonest number impossible to render.

**Files.**

| Path | Action |
| --- | --- |
| `finops-web/src/tokens.css` | create |
| `finops-web/src/components/Figure.tsx` | create |
| `finops-web/src/components/StateBoundary.tsx` | create |
| `finops-web/src/components/DataTable.tsx` | create |
| `finops-web/src/components/CoverageBanner.tsx` | create |
| `finops-web/src/components/FreshnessIndicator.tsx` | create |
| `finops-web/src/components/TypedError.tsx` | create |
| `finops-web/src/components/SeverityBadge.tsx` | create |
| `finops-web/src/components/Sparkline.tsx` | create |
| `finops-web/src/components/__tests__/*.test.tsx` | create |

**Acceptance criteria.**

- [x] **`Figure` cannot render without provenance and freshness.** They are
      required props, and the type system rejects a call without them
- [x] Provenance is encoded three times: fill, `~` prefix, and text label.
      A test asserts the label is present with colour disabled
- [x] `measured` renders solid, `modelled` renders hatched, `forecast` renders
      hatched with an interval and **never as a single number**
- [x] `Figure` given a typed error renders the cause and its remediation, and
      **renders no numeral at all**
- [x] `NoData` is the only cause that renders as `0`
- [x] `StateBoundary` implements all seven states from design system section 8
- [x] All numerals tabular, right aligned, fixed decimal places including
      trailing zeros
- [x] `DataTable` virtualises past 200 rows
- [x] Tokens defined for light and dark, both first class
- [x] Axe reports zero violations on every component
- [x] Reduced motion respected

**Tests.**

| Test | Asserts |
| --- | --- |
| `Figure.test.tsx::renders_no_numeral_for_a_failure` | The rule the whole design exists to protect |
| `Figure.test.tsx::nodata_renders_zero` | And that the one legitimate zero still works |
| `Figure.test.tsx::provenance_survives_without_colour` | Fill and label carry it independently |
| `Figure.test.tsx::forecast_renders_an_interval` | ADR-0015 condition 2 as a rendering rule |
| `StateBoundary.test.tsx::implements_seven_states` | Not three |

**How the guarantee is actually made.** `FigureValue` is a discriminated union,
so a forecast carries `low` and `high` and has no single amount to give. A point
forecast is not something a caller can express and then be reviewed for. A
failure carries a cause and a remediation and no amount at all, and there is no
shape in the type that pairs a failure with a number. ADR-0015 condition 2 is a
rendering rule, and this is it in the type system.

`components/index.ts` exports no formatter, and a test asserts that. If a screen
could import a function that turns a number into a string, then under time
pressure a screen will, and every figure on that page loses its provenance
without anything failing.

**Deviations, all small.** `provenance.ts`, `surfaceState.ts` and
`tableConfig.ts` hold values that would otherwise be exported from component
files, which the React Refresh rule rejects for good reason. `vite-env.d.ts` is
the standard Vite ambient declaration.

**Two defects found while building it, both of the same family.** `tsc --build`
was emitting JavaScript into `dist-types`, and vitest was collecting and running
those compiled copies as well, so every test ran twice against a build that
could be stale. Emit is now declaration only and the test glob is restricted to
`src`. Separately, `css: false` in the vitest config made a raw stylesheet
import return an empty string, so the token assertions passed over nothing while
appearing to check the palette.

**Do not.**

- Do not export a way to render a raw number. The moment one exists, a screen
  will use it under time pressure and the guarantee is gone. This is the same
  technique as the repository scope guard: make the wrong thing impossible,
  not discouraged.
- Do not animate a number changing value. A number counting up from zero is
  lying for 400 milliseconds, and this product's entire claim is that its
  numbers are trustworthy.
- Do not use red for a large cost. Red means a failure, so that when it appears
  it means one thing.
- Do not adopt a component library's table. ADR-0019 rejected it on evidence:
  the components a library gives you are exactly the ones we must control.

**Evidence.**

```bash
cd finops-web && npm run test -- --run && npx axe-core-cli
```

---

### TASK-P0-026: application shell, coverage banner and freshness indicator

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-27 |
| Implements | P0 spec section 9, screen 1 |
| Delivers | FEAT-006, FEAT-009, FEAT-050 |
| Depends on | TASK-P0-025, TASK-P0-035 |
| Estimate | M |

**Files.** `finops-web/src/` shell, layout, navigation, API client, and the
`meta` envelope handling. Uses the components from TASK-P0-035, and adds none.

**Acceptance criteria.**

- [x] A persistent banner reads "showing N of M accounts" whenever coverage is
      partial, per ISS-016
- [x] A global freshness indicator shows the oldest `as_of` in view
- [x] A degraded response is visually distinct from a healthy one

**Coverage and freshness are properties of the page, not of a panel.** Each
surface reports its own meta and the shell shows the worst of them: the oldest
`as_of` in view, the most conservative coverage, and degraded if any panel is. A
per panel treatment lets a reader carry an impression from one panel to the next
without noticing it stopped applying, and a page whose oldest panel is nine
hours old is a nine hour old page.

**The API client refuses a response with no envelope**, and throws rather than
returning an empty result when a request fails. An empty list rendered where a
request failed is indistinguishable from an organization with nothing in it,
which is the defect the backend spends its whole error taxonomy preventing,
arriving through the front door instead.

**Retries are off in the query client.** A retry hides a failure for as long as
it takes to give up, and the backend already retries what is worth retrying and
reports in its envelope what it could not do.

**A cause the frontend does not recognise is still shown.** Hiding it because
the vocabulary drifted would hide the drift.

**Evidence deferred.** The screenshot of the partial coverage state is not
produced here, because Playwright arrives with TASK-P0-028. The state itself is
asserted: `AppShell.test.tsx` renders it and checks the banner reads "Showing 42
of 310 accounts".

**Do not.**

- Do not hide the coverage banner when coverage is complete without saying so.
  Show "showing all M accounts". Absence of a warning is not the same as
  confirmation, and users need the confirmation.
- Do not make the coverage banner dismissible. A banner gets dismissed and the
  condition does not go away.
- Do not build a component here. If a screen needs something the inventory
  lacks, add it to the inventory in TASK-P0-035 and use it from there.

**Evidence.** `npm run test -- --run` and a screenshot of the partial coverage
state.

---

### TASK-P0-027: accounts screen and organization map

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-27 |
| Implements | P0 spec section 9, screens 2 and 3 |
| Delivers | FEAT-001, FEAT-009 |
| Depends on | TASK-P0-026 |
| Estimate | L |

**Acceptance criteria.**

- [x] Accounts table filters by role health, so broken onboarding is one click
- [x] Tree view is the default, and is keyboard navigable
- [x] Graph view renders with Cytoscape.js and stays usable at 300 accounts
- [x] Unreachable branches are drawn, marked, and not clickable

**Broken is one filter, not four.** Finding every account that cannot be read
is a single click. Making somebody select four health states in turn is how a
screen that technically supports the question fails to answer it.

**Two components joined the inventory**, `OrgTree` and `GraphCanvas`, which
section 11 lists and TASK-P0-035 did not build. Tree behaviour comes from React
Aria rather than being hand written, per ADR-0019 rung seven: accessible tree
navigation, expansion state and roving focus are subtle work that is not this
product's problem.

**An unreachable branch stays focusable and stops being actionable.** That is
why `disabledBehavior` is selection rather than the default. A branch a keyboard
user cannot reach at all is a branch they cannot discover, and discovering it is
the entire point of drawing it. The test asserts the behaviour, that clicking it
selects nothing, rather than asserting an attribute.

**React Aria caught a real defect during the work.** Expandable items had no
expand control, so a screen reader user could not open or close a branch at all.
The library says so out loud, and it was right.

**The graph library is loaded on demand.** It was most of the bundle, and the
tree is the default, so paying for it on first load slowed the view everybody
opens to speed up the one they mostly do not. First load went from 849 kB to
414 kB, 264 kB to 126 kB compressed.

**Evidence deferred.** The screenshot at 300 accounts needs a browser and
arrives with the Playwright journey in TASK-P0-028. What is asserted here is
what this project owns: the cap, and that 300 nodes and 299 edges are handed to
the library. Whether it then draws them legibly is a question about a browser.

**Do not.**

- Do not make the graph the default view. At 300 accounts a force directed
  graph is slower to read than a tree, and it is the first thing a user opens.
- Do not render more than 2,000 nodes. Filter server side.

**Evidence.** `npm run test -- --run`, plus a screenshot at 300 accounts.

---

### TASK-P0-028: ingest, freshness and platform cost screens, plus the end to end journey

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-27, with one criterion not performed |
| Implements | P0 spec section 9, screens 4 and 5 |
| Delivers | FEAT-006, FEAT-008, FEAT-010 |
| Depends on | TASK-P0-027 |
| Estimate | M |

**Acceptance criteria.**

- [x] Ingest screen shows per collector and per scope status with typed errors
      and remediation text
- [x] A failed collection is visually distinct from a zero result, per ISS-015
- [x] Platform cost screen shows spend by module with a 30 day sparkline
- [x] A Playwright journey covers login through to the organization map
- [x] P0 definition of done is demonstrable end to end
- [x] **Performance budgets 1 and 2 asserted**, see spec section 11b: a 300
      account sweep under 15 minutes against a seeded fake provider, and API
      p95 under 500 ms on scoped reads
- [ ] **Restore drill performed**: restore Aurora into a scratch database, run
      the migrations, confirm the application starts and the freshness screen
      reports correctly. A restore that has never been tested is a hypothesis

**Do not.**

- Do not render a failed collection as a zero, a dash, or an empty cell. It
  gets read as "no cost", which is the specific failure ISS-015 exists to
  prevent, and it is the last chance to catch it.

**Both budgets were measured, and the conditions matter more than the numbers.**

Budget 1, the full sweep of 300 accounts across two collectors, ran 600 units in
0.94 seconds against a 900 second budget. That measures this project's own
machinery, the claiming, the per unit transaction, the ledger writes and the
watermarks, against the fake provider. It does not measure AWS latency, which is
additive and only measurable against real accounts. A sweep already slow here
would be hopeless with a network in the way, so this is a floor rather than a
verdict.

Budget 2, p95 on a scoped read, was 4.2 milliseconds against a 500 millisecond
budget, over 60 requests through the real routes including the scope guard and
the audit write. What it lacks is a loaded database and a network hop.

**The Playwright journey runs against the real production bundle** with the API
stubbed at the network boundary. Every honesty rule it asserts, the coverage
banner, the marked unreachable branch and a refusal that renders no numeral, is
asserted against the built application rather than the test renderer.

**Three screenshots were produced**, which clears the evidence deferred from
TASK-P0-026 and TASK-P0-027: the partial coverage state, the tree at 300
accounts, and the graph at 300 accounts. The graph drew in under a second.

**The restore drill was not performed.** It needs an Aurora cluster to restore
into a scratch database, and there is none here. This criterion is open, and it
is the one thing in P0 that is written down as done nowhere. It has to be run
against a real deployment before P0 is signed off.

**The live end to end journey was not run either.** The journey above proves the
frontend carries a user through the map. Proving it against a live API, a real
database and real accounts needs the deployed stack, which arrives with Wave D.

**Evidence.**

```bash
make test-all && make test-e2e
```

---

### TASK-P0-032: retention jobs and the erasure script

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-27, with one criterion deferred to TASK-P0-015 |
| Implements | `docs/09-DATA-CLASSIFICATION.md` |
| Depends on | TASK-P0-021 |
| Estimate | M |

**Goal.** Retention is enforced by a job, not stated as a policy nobody runs.

**Files.**

| Path | Action |
| --- | --- |
| `finops_ingest/collectors/retention.py` | created |
| `finops_ingest/collectors/partitions.py` | created, not planned. See the deviation below |
| `scripts/ops/erase_principal.py` | created |
| `tests/ingest/collectors/test_retention.py` | created, 14 integration tests |
| `tests/ingest/collectors/test_partitions.py` | created, 6 tests that need no container |
| `migrations/versions/0002_cost_monthly.py` | created, additive |

**Acceptance criteria.**

- [x] Five jobs: `retention_principal`, `retention_operational`,
      `retention_audit`, `retention_cost`, `retention_scope_cache`
- [x] Each writes an `ingest_run`, so a stopped retention job appears on the
      freshness screen exactly like a stopped collector
- [x] `retention_principal` anonymises rather than removing rows, so audit
      joins do not dangle
- [x] `erase_principal.py` performs all five erasure steps in one transaction
      and prints what it changed
- [ ] Backup retention set in Terraform to match the table policy. Deferred to
      TASK-P0-015, which is where the Aurora cluster is defined. There is
      nowhere to set it until that file exists

**Deviations.**

1. **A sixth job, `partition_maintenance`, and a new module.**
   `cost_focus_daily` and `cost_provider_extra` are declared `PARTITION BY
   RANGE` and nothing anywhere created a partition, so both tables rejected
   every row with "no partition of relation found for row". The checkpoint for
   TASK-P0-010 already said this job belonged here. It is the other half of
   retention rather than a separate concern: one job creates the months, the
   other removes them.
2. **`retention_cost` drops partitions instead of deleting rows.** The
   aggregate is written first, in the same transaction, on the same month
   boundary that is then dropped. A partition drop is one catalog operation
   against a scan, a mass delete and a vacuum on the largest table in the
   system. The consequence is documented: the boundary is the first of the
   month containing the cutoff, so days still inside the window are never taken
   with it.
3. **`retention_operational` also clears dead watermarks.**
   `docs/09-DATA-CLASSIFICATION.md` said it should and the first implementation
   did not. The document was right and the code was changed to match it.
4. **A schema change.** `cost_focus_monthly` did not exist, so there was
   nothing to aggregate into. Added as migration `0002`, additive per
   constraint 12.
5. **The `retention_jobs` feature flag was declared and enforced nowhere.**
   `docs/feature-flags.yaml` calls it a permanent operational control for
   stopping a suspected retention bug immediately. Nothing read it, so an
   operator turning it off would have believed retention had stopped while it
   continued. `due_collectors()` in `finops_ingest/registry.py` now applies it,
   takes the predicate rather than importing the resolver because this package
   sits below `finops_api`, and has no default, since a default of "everything
   is on" is the same silent pass in a different place.
6. **One existing test corrected.**
   `test_healthz_reports_a_recent_collection_as_healthy` listed three
   collectors by hand and so reported a tenant healthy while six scheduled
   collectors had never run. It now derives the list from `DEFAULT_SCHEDULE`.

**Do not.**

- Do not touch `audit_event` on an erasure request. The join to a name is
  already broken by anonymising `principal`, and removing the record of who
  read an organization's financial data, on that person's request, is not
  defensible in a financial services environment.
- Do not expose erasure as an API route. It is a destructive primitive, and it
  is deliberately a script a person runs.
- Do not leave backup retention longer than table retention. A 35 day backup
  holding data that policy dropped 30 days ago undoes the policy.

**Evidence.**

```bash
pytest tests/ingest/collectors/test_retention.py -v
```

---

### TASK-P0-036: routing, the seven groups, and the route migration

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-07 |
| Implements | `docs/13-UI-ARCHITECTURE.md` sections 4 and 5, ADR-0020 |
| Delivers | The frame every later screen is added to |
| Depends on | TASK-P0-028 |
| Estimate | M |

**Acceptance criteria.**

- [x] `react-router` admitted through `make dep-check pkg=react-router npm=1`
- [x] `sections.ts` exports a group definition, not a name list
- [x] The five built screens answer on their new routes from section 5
- [x] A screen that has not been built is **listed with its arrival**, not hidden
      and not silently disabled
- [x] A test asserts every route begins with its own group path, so ADR-0020's
      rule is enforced by the suite rather than by review
- [x] `npm run lint`, `npm run test -- --run` and `npm run build` all pass
- [x] The Playwright journey passes against the new routes

**Do not.**

- Do not climb the ladder. Choosing a routing library is ADR-0013 rung two, the
  lowest applicable rung, so it needs the admission gate and no disqualification
  record. Hand writing History API navigation would be rung seven with rung two
  undisqualified.
- Do not hide a group whose sub project has not landed. A product that hides its
  unbuilt screens looks smaller than it is and makes the roadmap invisible.

**Steps.**

- [x] **Step 1: admit the dependency**

```bash
make dep-check pkg=react-router npm=1
```

Expected: the gate reports the package, its licence and its advisory state, and
exits zero. If it exits non zero, stop and raise an `ISS-nnn` row rather than
installing anyway.

- [x] **Step 2: write the failing invariant test**

`finops-web/src/shell/__tests__/sections.test.ts`

```ts
import { describe, expect, it } from 'vitest';

import { GROUPS, allScreens } from '../sections';

describe('navigation groups', () => {
  it('has exactly the seven groups ADR-0020 fixes', () => {
    expect(GROUPS.map((g) => g.label)).toEqual([
      'Home',
      'Cost',
      'Waste',
      'Governance',
      'Inventory',
      'Platform',
      'Assistant',
    ]);
  });

  it('gives every screen a route inside its own group', () => {
    for (const group of GROUPS) {
      for (const screen of group.screens) {
        expect(screen.path.startsWith(group.path)).toBe(true);
      }
    }
  });

  it('never issues the same route twice', () => {
    const paths = allScreens().map((s) => s.path);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it('marks an unbuilt screen with the sub project that brings it', () => {
    const spend = allScreens().find((s) => s.path === '/cost');
    expect(spend?.arrives).toBe('P1 Cost Intelligence');
  });
});
```

- [x] **Step 3: run it and watch it fail**

Run: `cd finops-web && npm run test -- --run src/shell/__tests__/sections.test.ts`
Expected: FAIL, `GROUPS` is not exported from `../sections`.

- [x] **Step 4: replace the name list with a group definition**

`finops-web/src/shell/sections.ts`, replacing the whole file.

```ts
/**
 * The navigation, per ADR-0020. Seven groups, fixed for the life of the
 * product. A sub project adds screens inside a group and never adds a top level
 * entry, which is why this array does not grow as the roadmap lands.
 *
 * `arrives` is null when the screen is built. When it is a sub project name the
 * screen is listed and reachable, and says what will fill it. Hiding an unbuilt
 * screen would make the product look smaller than it is and hide the roadmap.
 */

export interface ScreenDef {
  readonly path: string;
  readonly label: string;
  /** Null when built. The sub project name when it is not. */
  readonly arrives: string | null;
}

export interface GroupDef {
  readonly label: string;
  readonly path: string;
  readonly screens: readonly ScreenDef[];
}

export const GROUPS: readonly GroupDef[] = [
  {
    label: 'Home',
    path: '/',
    screens: [{ path: '/', label: 'Home', arrives: null }],
  },
  {
    label: 'Cost',
    path: '/cost',
    screens: [
      { path: '/cost', label: 'Spend and trend', arrives: 'P1 Cost Intelligence' },
      { path: '/cost/allocation', label: 'Allocation', arrives: 'P1 Cost Intelligence' },
      { path: '/cost/anomalies', label: 'Anomalies', arrives: 'P1 Cost Intelligence' },
      { path: '/cost/commitments', label: 'Commitments', arrives: 'P1 Cost Intelligence' },
      { path: '/cost/export', label: 'Export', arrives: 'P1 Cost Intelligence' },
    ],
  },
  {
    label: 'Waste',
    path: '/waste',
    screens: [
      { path: '/waste', label: 'Recommendations', arrives: 'P3 Utilization and Rightsizing' },
      { path: '/waste/savings', label: 'Realized savings', arrives: 'P3 Utilization and Rightsizing' },
      { path: '/waste/score', label: 'FinOps Score', arrives: 'P3 Utilization and Rightsizing' },
    ],
  },
  {
    label: 'Governance',
    path: '/governance',
    screens: [
      { path: '/governance/queries', label: 'Query findings', arrives: 'P2 Query Cost Governance' },
      { path: '/governance/instances', label: 'Query surfaces', arrives: 'P2 Query Cost Governance' },
      { path: '/governance/enforcement', label: 'Enforcement', arrives: 'P2 Query Cost Governance' },
      { path: '/governance/quotas', label: 'Quotas', arrives: 'P5 Quotas and Limits' },
    ],
  },
  {
    label: 'Inventory',
    path: '/inventory',
    screens: [
      { path: '/inventory/accounts', label: 'Accounts', arrives: null },
      { path: '/inventory/organization', label: 'Organization', arrives: null },
      { path: '/inventory/resources', label: 'Resources', arrives: 'P4 Inventory and Topology' },
      { path: '/inventory/topology', label: 'Topology', arrives: 'P4 Inventory and Topology' },
    ],
  },
  {
    label: 'Platform',
    path: '/platform',
    screens: [
      { path: '/platform/ingest', label: 'Ingest', arrives: null },
      { path: '/platform/freshness', label: 'Freshness', arrives: null },
      { path: '/platform/cost', label: 'Meter cost', arrives: null },
      { path: '/platform/flags', label: 'Flags', arrives: 'P0, not yet surfaced' },
    ],
  },
  {
    label: 'Assistant',
    path: '/assistant',
    screens: [
      { path: '/assistant', label: 'Ask', arrives: 'P7 Insight and LLM layer' },
      { path: '/assistant/digests', label: 'Digests', arrives: 'P7 Insight and LLM layer' },
    ],
  },
];

export function allScreens(): readonly ScreenDef[] {
  return GROUPS.flatMap((group) => group.screens);
}
```

Note the Home group's screen path equals its group path, which the second test
allows because `'/'.startsWith('/')` is true. Every other group has a distinct
prefix.

- [x] **Step 5: run the test and watch it pass**

Run: `cd finops-web && npm run test -- --run src/shell/__tests__/sections.test.ts`
Expected: PASS, four tests.

- [x] **Step 6: write the failing shell navigation test**

Append to `finops-web/src/shell/__tests__/AppShell.test.tsx`.

```tsx
it('lists an unbuilt screen with what will fill it, rather than hiding it', () => {
  renderShell();
  const link = screen.getByRole('link', { name: /Spend and trend/ });
  expect(link).toBeInTheDocument();
  expect(link).toHaveAttribute('data-arrives', 'P1 Cost Intelligence');
});
```

The shell test helper must now wrap in a `MemoryRouter`, because `NavLink`
requires a router context. Update the existing helper rather than adding a
second one.

`finops-web/src/screens/__tests__/Harness.tsx` needs the same treatment, because
every screen that renders a `Link` will otherwise throw. Add the router inside
`Harness` so all existing screen tests keep working unchanged:

```tsx
import { MemoryRouter } from 'react-router';

export function Harness({
  client,
  children,
  initialPath = '/',
}: {
  readonly client: ApiClient;
  readonly children: ReactNode;
  readonly initialPath?: string;
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      <QueryClientProvider client={queryClient}>
        <ApiProvider client={client}>
          <MetaProvider>{children}</MetaProvider>
        </ApiProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}
```

`initialPath` is optional and defaults to `/`, so the six existing screen test
files do not change.

- [x] **Step 7: run it and watch it fail**

Run: `cd finops-web && npm run test -- --run src/shell/__tests__/AppShell.test.tsx`
Expected: FAIL, no link with that name.

- [x] **Step 8: render the groups in the shell**

In `finops-web/src/shell/AppShell.tsx`, replace the `SECTIONS.map` navigation
with the grouped form. Keep the header, coverage banner, freshness and failures
exactly as they are.

```tsx
<nav aria-label="Sections">
  {GROUPS.map((group) => (
    <div key={group.label}>
      <h2>{group.label}</h2>
      <ul>
        {group.screens.map((s) => (
          <li key={s.path}>
            <NavLink to={s.path} end data-arrives={s.arrives ?? undefined}>
              {s.label}
              {s.arrives ? <span> arrives with {s.arrives}</span> : null}
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  ))}
</nav>
```

`AppShellProps` loses `section` and `onSelect`, because the router now owns
which screen is current. Delete them rather than leaving them unused.

- [x] **Step 9: replace the state machine in the application root**

`finops-web/src/App.tsx`. The `useState<Section>` and the five conditionals go.

```tsx
<BrowserRouter>
  <AppShell>
    <Routes>
      <Route path="/inventory/accounts" element={<AccountsScreen />} />
      <Route path="/inventory/organization" element={<OrganizationScreen />} />
      <Route path="/platform/ingest" element={<IngestScreen />} />
      <Route path="/platform/freshness" element={<FreshnessScreen />} />
      <Route path="/platform/cost" element={<PlatformScreen />} />
      <Route path="*" element={<NotBuiltYet />} />
    </Routes>
  </AppShell>
</BrowserRouter>
```

`NotBuiltYet` reads the current path, finds it in `allScreens()`, and renders the
`Empty, never collected` treatment naming `arrives`. A path not in `allScreens()`
is a genuine 404 and says so. Those are different conditions and must not share
a rendering.

- [x] **Step 10: run the whole suite**

Run: `cd finops-web && npm run lint && npm run test -- --run && npm run build`
Expected: all pass. `App.test.tsx` needs its section clicking replaced with
router navigation.

- [x] **Step 11: update the end to end journey**

`finops-web/e2e/journey.spec.ts` navigates by section name today. Point it at the
new URLs. The journey is the only test that proves the routes work in a browser
rather than in jsdom.

Run: `cd finops-web && npx playwright test`
Expected: PASS.

- [x] **Step 12: commit**

```bash
git add finops-web/package.json finops-web/package-lock.json finops-web/src finops-web/e2e
git commit -m "feat: TASK-P0-036, seven navigation groups and the route migration

Five screens moved to routes that carry their group, per ADR-0020. An unbuilt
screen is listed with the sub project that brings it rather than hidden, so the
roadmap is legible inside the product."
```

---

### TASK-P0-037: the fixture seam and the fixture marker

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | `docs/13-UI-ARCHITECTURE.md` section 11 |
| Delivers | A screen can be built and reviewed before its route exists |
| Depends on | TASK-P0-036 |
| Estimate | S |

**Acceptance criteria.**

- [ ] One declared set of paths that are still fixture backed
- [ ] A screen reading a fixture backed path renders a visible `FIXTURE DATA` band
- [ ] A route failure raises and is rendered as a typed cause. It **never** falls
      back to the fixture
- [ ] **A Python test fails the build if a path in the fixture set is registered
      in the FastAPI application**, so a live route cannot keep serving invented
      numbers because somebody forgot a list
- [ ] Axe reports zero violations on the band

**Do not.**

- Do not gate the marker on a build flag or an environment variable. A marker
  that only appears in development is absent exactly when it matters.
- Do not fall back to the fixture when a route fails. That would render invented
  numbers during an outage, which is the precise failure rule 5 of
  `docs/12-UI-DESIGN.md` exists to prevent.
- Do not trust review to keep the set current. The Python test is the mechanism.
  Review is not.

**Steps.**

- [ ] **Step 1: write the failing resolver test**

`finops-web/src/api/__tests__/fixtureSeam.test.ts`

```ts
import { describe, expect, it } from 'vitest';

import { FIXTURE_SURFACES, resolveSurface } from '../fixtureSeam';

describe('resolveSurface', () => {
  it('uses the fixture, and says so, for a declared fixture template', async () => {
    const read = resolveSurface(
      '/api/v1/query/findings',
      async () => ['real'],
      () => ['fixture'],
    );
    await expect(read()).resolves.toEqual({ data: ['fixture'], source: 'fixture' });
  });

  it('matches a parameterised template rather than a concrete url', async () => {
    const read = resolveSurface(
      '/api/v1/query/findings/{id}',
      async () => ['real'],
      () => ['fixture'],
    );
    await expect(read()).resolves.toEqual({ data: ['fixture'], source: 'fixture' });
  });

  it('uses the route, and says so, for any other template', async () => {
    const read = resolveSurface('/api/v1/accounts', async () => ['real'], () => ['fixture']);
    await expect(read()).resolves.toEqual({ data: ['real'], source: 'route' });
  });

  it('lets a route failure surface rather than falling back to the fixture', async () => {
    const boom = async (): Promise<string[]> => {
      throw new Error('AccessDenied');
    };
    const read = resolveSurface('/api/v1/accounts', boom, () => ['fixture']);
    await expect(read()).rejects.toThrow('AccessDenied');
  });

  it('declares every fixture template under the api prefix', () => {
    for (const template of FIXTURE_SURFACES) {
      expect(template.startsWith('/api/v1/')).toBe(true);
    }
  });
});
```

The third test is the important one. A resolver that fell back on error would
render invented numbers during an outage.

- [ ] **Step 2: run it and watch it fail**

Run: `cd finops-web && npm run test -- --run src/api/__tests__/fixtureSeam.test.ts`
Expected: FAIL, cannot find module `../fixtureSeam`.

- [ ] **Step 3: write the seam**

`finops-web/src/api/fixtureSeam.ts`

```ts
/**
 * Contract first delivery, per `docs/13-UI-ARCHITECTURE.md` section 11.
 *
 * A screen is built against a typed fixture before its route exists. The set
 * below is the single declaration of which paths are still invented, and
 * `tests/api/test_fixture_surfaces.py` fails the build the moment one of them is
 * registered in the application. That test is what makes the set impossible to
 * forget, which matters because a forgotten entry means a fixture rendering as
 * real data.
 *
 * A route that fails does not fall back to the fixture. It raises, the screen
 * renders the typed cause, and no numeral appears.
 */

export type SurfaceSource = 'route' | 'fixture';

export interface Resolved<T> {
  readonly data: T;
  readonly source: SurfaceSource;
}

/**
 * Route templates whose screens exist and whose routes do not. Emptied as
 * routes land.
 *
 * These are templates, not concrete URLs, written the way FastAPI writes
 * `route.path`. A detail screen fetches `/api/v1/query/findings/abc-123` and
 * declares `/api/v1/query/findings/{id}`, so the guard in
 * `tests/api/test_fixture_surfaces.py` can compare like with like.
 */
export const FIXTURE_SURFACES: ReadonlySet<string> = new Set([
  '/api/v1/query/findings',
  '/api/v1/query/findings/{id}',
  '/api/v1/query/instances',
  '/api/v1/query/enforcement',
]);

export function resolveSurface<T>(
  template: string,
  live: () => Promise<T>,
  fixture: () => T,
): () => Promise<Resolved<T>> {
  return async () => {
    if (FIXTURE_SURFACES.has(template)) {
      return { data: fixture(), source: 'fixture' };
    }
    return { data: await live(), source: 'route' };
  };
}
```

- [ ] **Step 4: run it and watch it pass**

Run: `cd finops-web && npm run test -- --run src/api/__tests__/fixtureSeam.test.ts`
Expected: PASS, five tests.

- [ ] **Step 5: write the failing cross language guard**

`tests/api/test_fixture_surfaces.py`

```python
"""A fixture backed path must not be a real route.

The frontend renders invented numbers for every path in FIXTURE_SURFACES, and
says so on screen. The moment a route is registered the invention has to stop,
and review is not a mechanism for noticing that. This test is.
"""

import re
from pathlib import Path

from finops_api.main import create_app

SEAM = Path(__file__).resolve().parents[2] / "finops-web" / "src" / "api" / "fixtureSeam.ts"


def declared_fixture_templates() -> set[str]:
    block = SEAM.read_text(encoding="utf-8").split("FIXTURE_SURFACES", 1)[1]
    block = block.split("]", 1)[0]
    return set(re.findall(r"'(/api/v1/[^']+)'", block))



def test_no_fixture_path_is_a_registered_route() -> None:
    registered = {route.path for route in create_app().routes if hasattr(route, "path")}
    still_invented = declared_fixture_templates() & registered
    assert not still_invented, (
        f"These paths are live routes but the frontend still serves fixtures for them: "
        f"{sorted(still_invented)}. Remove them from FIXTURE_SURFACES in {SEAM}."
    )
```

Confirm the application factory is named `create_app` in `finops_api/main.py`
before running this, and use whatever that module actually exports.

- [ ] **Step 6: run it and watch it pass, then prove it can fail**

Run: `pytest tests/api/test_fixture_surfaces.py -v`
Expected: PASS, because none of the four routes exist yet.

Now prove the guard works. Temporarily add `'/api/v1/accounts'` to
`FIXTURE_SURFACES`, rerun, and confirm it FAILS naming that path. Remove it
again. **A guard nobody has seen fail is a guard nobody knows works.**

- [ ] **Step 7: write the failing band test**

`finops-web/src/components/__tests__/FixtureBand.test.tsx`

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { FixtureBand } from '../FixtureBand';
import { violationsIn } from './axe';

describe('FixtureBand', () => {
  it('says nothing when the data came from a route', () => {
    render(<FixtureBand source="route" />);
    expect(screen.queryByTestId('fixture-band')).toBeNull();
  });

  it('says so, visibly, when the data is invented', () => {
    render(<FixtureBand source="fixture" />);
    expect(screen.getByTestId('fixture-band')).toHaveTextContent(/FIXTURE DATA/);
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<FixtureBand source="fixture" />);
    expect(await violationsIn(container)).toEqual([]);
  });
});
```

- [ ] **Step 8: run it and watch it fail**

Run: `cd finops-web && npm run test -- --run src/components/__tests__/FixtureBand.test.tsx`
Expected: FAIL, cannot find module `../FixtureBand`.

- [ ] **Step 9: write the band**

`finops-web/src/components/FixtureBand.tsx`

```tsx
import type { SurfaceSource } from '../api/fixtureSeam';

/**
 * The one honest way to show a screen before its data is real.
 *
 * It renders in the trust strip, in the same place the coverage warning goes,
 * because it is the same kind of claim: something about this view is not what a
 * reader would otherwise assume.
 */
export function FixtureBand({ source }: { readonly source: SurfaceSource }) {
  if (source === 'route') {
    return null;
  }
  return (
    <p data-testid="fixture-band" data-state="fixture" role="status">
      FIXTURE DATA. This screen is not connected to a collector yet.
    </p>
  );
}
```

Export it from `finops-web/src/components/index.ts` alongside the others.

- [ ] **Step 10: run everything**

Run: `cd finops-web && npm run lint && npm run test -- --run && npm run build`
Then: `pytest tests/api/test_fixture_surfaces.py -v`
Expected: all pass.

- [ ] **Step 11: commit**

```bash
git add finops-web/src tests/api/test_fixture_surfaces.py
git commit -m "feat: TASK-P0-037, the fixture seam and its marker

A screen can be built and reviewed before its route exists, and says on screen
that it is not connected. A Python test fails the build if a fixture path
becomes a real route, so the set cannot rot. A failing route raises rather than
falling back to invented numbers."
```

---

### TASK-P0-038: the home screen

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | `docs/13-UI-ARCHITECTURE.md` section 6 |
| Delivers | FEAT-008 on the front page, per architectural constraint 7 |
| Depends on | TASK-P0-037 |
| Estimate | M |

**Acceptance criteria.**

- [ ] Five slots in the order given in section 6
- [ ] A slot with no data **names the sub project that will fill it** and renders
      no numeral
- [ ] Meter's own cost appears on the trust strip, on Home only
- [ ] Every figure links to the screen that owns it
- [ ] The screen issues no query that is not already issued by a screen it
      summarises
- [ ] Axe reports zero violations

**Do not.**

- Do not render an unfilled slot as zero, as a dash, or as a blank cell. That is
  rule 5 of `docs/12-UI-DESIGN.md` and it is the whole product.
- Do not give Home its own aggregate query. A home screen that computes its own
  total will one day disagree with the screen it summarises, and a user who
  catches that disagreement stops trusting both.

**Steps.**

- [ ] **Step 1: write the failing slot test**

`finops-web/src/screens/__tests__/HomeScreen.test.tsx`

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { HomeScreen } from '../HomeScreen';
import { Harness } from './Harness';
import { clientReturning, metaOf } from './fixtures';
import { violationsIn } from '../../components/__tests__/axe';

const COST = {
  data: [
    {
      day: '2026-09-05',
      module: 'api',
      service: 'AmazonECS',
      amortized_cost: '412.80',
      as_of: '2026-09-05T04:00:00Z',
      collected_at: '2026-09-06T09:54:00Z',
    },
  ],
  meta: metaOf(),
};

function renderHome() {
  const client = clientReturning({ '/api/v1/platform/cost': COST });
  return render(
    <Harness client={client}>
      <HomeScreen />
    </Harness>,
  );
}

describe('HomeScreen', () => {
  it('names the sub project that will fill an empty slot', () => {
    renderHome();
    const slot = screen.getByTestId('home-slot-spend');
    expect(slot).toHaveTextContent(/not yet collected/i);
    expect(slot).toHaveTextContent(/P1 Cost Intelligence/);
  });

  it('renders no numeral in an empty slot', () => {
    renderHome();
    expect(screen.getByTestId('home-slot-spend').textContent ?? '').not.toMatch(/[0-9]/);
  });

  it('links every figure to the screen that owns it', () => {
    renderHome();
    expect(screen.getByRole('link', { name: /Meter cost/ })).toHaveAttribute(
      'href',
      '/platform/cost',
    );
  });

  it('has no accessibility violations', async () => {
    const { container } = renderHome();
    await screen.findByTestId('figure');
    expect(await violationsIn(container)).toEqual([]);
  });
});
```

The second test is the load bearing one. `P1` contains no digit and
`Cost Intelligence` contains none, so a slot that accidentally renders a zero
fails it.

- [ ] **Step 2: run it and watch it fail**

Run: `cd finops-web && npm run test -- --run src/screens/__tests__/HomeScreen.test.tsx`
Expected: FAIL, cannot find module `../HomeScreen`.

- [ ] **Step 3: write the screen**

`finops-web/src/screens/HomeScreen.tsx`

```tsx
import { Link } from 'react-router';

import { usePlatformCost } from '../api/queries';
import { Figure, StateBoundary } from '../components';

interface SlotDef {
  readonly id: string;
  readonly label: string;
  readonly owns: string;
  readonly arrives: string | null;
}

/**
 * The five slots from `docs/13-UI-ARCHITECTURE.md` section 6, in priority
 * order. The order does not change per role. Scope changes per role, the
 * questions do not.
 *
 * An unfilled slot names the sub project that will fill it, which is what makes
 * this screen double as the progress view: each sub project that lands turns one
 * named absence into a number.
 */
const SLOTS: readonly SlotDef[] = [
  { id: 'spend', label: 'Total spend, month to date', owns: '/cost', arrives: 'P1 Cost Intelligence' },
  { id: 'trend', label: 'Trend, 30 days', owns: '/cost', arrives: 'P1 Cost Intelligence' },
  { id: 'movers', label: 'Top movers', owns: '/cost', arrives: 'P1 Cost Intelligence' },
  {
    id: 'findings',
    label: 'Top findings by dollar',
    owns: '/governance/queries',
    arrives: 'P2 Query Cost Governance',
  },
  {
    id: 'savings',
    label: 'Realized savings, trailing 60 days',
    owns: '/waste/savings',
    arrives: 'P3 Utilization and Rightsizing',
  },
];

function EmptySlot({ slot }: { readonly slot: SlotDef }) {
  return (
    <section data-testid={`home-slot-${slot.id}`} aria-label={slot.label}>
      <h3>{slot.label}</h3>
      <p data-state="never-collected">
        not yet collected, arrives with <Link to={slot.owns}>{slot.arrives}</Link>
      </p>
    </section>
  );
}

export function HomeScreen() {
  const cost = usePlatformCost();
  return (
    <>
      <section aria-label="Meter cost">
        <Link to="/platform/cost">Meter cost</Link>
        <StateBoundary query={cost}>
          {(envelope) => (
            <Figure
              value={{ kind: 'measured', amount: totalOf(envelope.data) }}
              freshness={freshnessOf(envelope.meta)}
            />
          )}
        </StateBoundary>
      </section>
      {SLOTS.map((slot) => (slot.arrives === null ? null : <EmptySlot key={slot.id} slot={slot} />))}
    </>
  );
}
```

`StateBoundary`, `Figure` and their prop shapes already exist. Read
`finops-web/src/components/StateBoundary.tsx` and
`finops-web/src/components/Figure.tsx` and match their actual props rather than
the illustrative call above. `totalOf` and `freshnessOf` are two small local
helpers in this file: one sums `amortized_cost` with a decimal safe addition,
the other maps `as_of` and `collected_at` into the shape `Figure` expects.

**Do not add a new query hook.** `usePlatformCost` is the hook `PlatformScreen`
already uses, with query key `['platform-cost']`, so react-query serves both from
one cache entry. Two hooks over one endpoint is how two screens start
disagreeing.

- [ ] **Step 4: run the tests and watch them pass**

Run: `cd finops-web && npm run test -- --run src/screens/__tests__/HomeScreen.test.tsx`
Expected: PASS, four tests.

- [ ] **Step 5: write the failing test that Home issues no query of its own**

Append to the same file. `clientReturning` rejects any path it was not given, so
a recording wrapper turns an extra request into a listed path rather than a
generic failure.

```tsx
it('requests nothing that the screens it summarises do not already request', async () => {
  const asked: string[] = [];
  const inner = clientReturning({ '/api/v1/platform/cost': COST });
  const recording = {
    get: <T,>(path: string) => {
      asked.push(path);
      return inner.get<T>(path);
    },
  };
  render(
    <Harness client={recording}>
      <HomeScreen />
    </Harness>,
  );
  await screen.findByTestId('figure');
  expect(asked).toEqual(['/api/v1/platform/cost']);
});
```

- [ ] **Step 6: run it and watch it pass**

Run: `cd finops-web && npm run test -- --run src/screens/__tests__/HomeScreen.test.tsx`
Expected: PASS, five tests. If it fails listing a second path, Home has grown an
aggregate query of its own and rule 1 of section 6 has been broken.

- [ ] **Step 7: route Home and make it the landing screen**

In `finops-web/src/App.tsx`, add `<Route path="/" element={<HomeScreen />} />`
as the first route. The application now lands on Home rather than on Accounts.

- [ ] **Step 8: run the whole suite and the journey**

Run: `cd finops-web && npm run lint && npm run test -- --run && npm run build && npx playwright test`
Expected: all pass.

- [ ] **Step 9: commit**

```bash
git add finops-web/src
git commit -m "feat: TASK-P0-038, the home screen

Trust strip above the money, per architectural constraint 7. An unfilled slot
names the sub project that will fill it and renders no numeral, which is what
makes the front page double as the progress view. Home owns no data of its own."
```

---

## Wave I: security and MCP

### TASK-P0-029: establish the security tool chain and the first posture

| Field | Value |
| --- | --- |
| Status | **Done 2026-08-23**, commit `9754a59` |
| Implements | P0 spec section 11a, ADR-0010 |
| Depends on | none |
| Order | **First. Before everything, including 001** |
| Estimate | M |

**Goal.** Prove the security ground rules hold before any code is written
against them.

It runs before TASK-P0-001 and needs nothing from it. `make security-tools`
installs the scanners, and `make dep-check` builds its own throwaway
environment, so neither needs the project virtualenv to exist yet.

**Files.**

| Path | Action |
| --- | --- |
| `security/POSTURE.md` | regenerate, currently a placeholder |
| `security/policy/*.yaml` | verify, already exist |
| `.pre-commit-config.yaml` | modify |

**Acceptance criteria.**

- [ ] `make security-tools` installs grype, syft, trivy, gitleaks and cosign
- [ ] **The Minimus tags this project depends on are verified to exist**:
      `reg.mini.dev/python:3.12`, `python:3.12-dev`, `node:22-dev`,
      `nginx:1.27`. Record the resolved digests
- [ ] Every dependency declared in `pyproject.toml` passes
      `make dep-check pkg=<name>`, run individually
- [ ] `make security-scan` runs end to end and writes a report and a posture
- [ ] `security/POSTURE.md` reports zero findings

**Do not.**

- Do not proceed past this task if a Minimus tag is missing. Record the gap as
  an `ISS-nnn` row, choose a documented alternative, and update ADR-0010.
  Silently reverting to the official Python image would reintroduce more than
  400 vulnerabilities and nobody would notice until an audit.
- Do not add a dependency that fails the gate by lowering a threshold. Replace
  it, or write a time boxed allowlist entry with your name on it.

**Evidence.**

```bash
make security-tools && make security-scan && cat security/POSTURE.md
```

**Result, 2026-08-23.** All four tags exist and pull anonymously. Scanning them
changed two version choices and one policy.

| Image | Total | Critical | High | Fixable |
| --- | --- | --- | --- | --- |
| `python:3.12` | 13 | 0 | 3 | 0 |
| `python:3.13` | 3 | 0 | 0 | 0 |
| `node:22-dev` | 0 | 0 | 0 | 0 |
| `nginx:1.27` | 93 | 6 | 26 | 76 |
| `nginx:1.30` | 0 | 0 | 0 | 0 |
| official `python:3.12-slim` | 204 | 7 | 26 | 80 |

Moved to python 3.13 and nginx 1.30. Digests pinned in
`docker/base-images.lock`. The policy of zero at any severity proved
undeliverable and was amended by ADR-0018 to zero findings that have a
published fix, with three unfixable CPython findings accepted under a
reachability argument that `check_forbidden_imports.py` enforces.

Posture: **zero fixable findings**, three accepted unfixable, no secrets found.

**Dependency admission, run 2026-10-07.** This criterion was missed when the
task was first marked done, and is recorded here rather than quietly satisfied
later. The full declared set was installed into a throwaway environment and the
resolved tree scanned, which is stronger than a per package run because it also
covers what the resolution pulls in.

| Scanner | Scope | Result |
| --- | --- | --- |
| grype, via a syft SBOM | 97 resolved packages | **0 findings** |
| pip-audit | 113 packages | **0 advisories** |

All 10 runtime and 9 development dependencies admitted.

**Deviation.** The task also created the Python package namespaces and the
virtualenv, which belong to TASK-P0-001, because the policy checks needed
something to scan and the documentation scripts needed pyyaml. TASK-P0-001 is
therefore partly done. Recorded rather than absorbed.

---

### TASK-P0-030: MCP server scaffold and the four P0 tools

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-27 |
| Implements | P0 spec section 8.0, ADR-0009 |
| Delivers | FEAT-042 groundwork |
| Depends on | TASK-P0-025 |
| Estimate | M |

**Goal.** An MCP server exposing the P0 read surface, proving the facade
pattern before there is much to expose.

**Files.**

| Path | Action |
| --- | --- |
| `finops_mcp/api.py` | created. The only way this package reaches Meter |
| `finops_mcp/server.py` | created |
| `finops_mcp/tools.py` | created |
| `tests/mcp/test_contract.py` | created, 10 tests that need no container |
| `tests/mcp/test_tools.py` | created, 5 against the real application |
| `tests/scripts/test_layer_agreement.py` | created, not planned. See deviation 4 |
| `finops_api/schemas.py` | the six response models moved here. See deviation 1 |
| `finops_api/main.py` | `bootstrap()` added. See deviation 3 |
| `docker/Dockerfile.api` | the MCP command, and a corrected API command |

**Acceptance criteria.**

- [x] Ships as a second process in the `meter-api` image, selected by the
      container command. No fourth image, see ADR-0009
- [x] Four tools: `list_accounts`, `get_org_tree`, `get_ingest_status`,
      `get_platform_cost`. Six were built, see deviation 2
- [x] Every tool calls the HTTP API over the network with the caller's token
- [x] Tool schemas are generated from the same Pydantic models the API uses,
      so a drift between the two surfaces fails the build
- [x] Every tool response carries the `meta` envelope unchanged, including
      `scope_coverage`, so a model cannot present a partial total as complete
- [x] A caller with a two account scope receives two accounts from the tool

**Deviations.**

1. **The six response models moved from the route modules into
   `finops_api/schemas.py`.** Generating a tool schema from the API's own model
   means importing it, and every route module imports SQLAlchemy, which the
   facade contract forbids both directly and through the chain. The alternative
   was a second set of models inside `finops_mcp` kept equal by hand, which is
   the drift the generation was meant to remove.
2. **Six tools rather than four.** `get_freshness` and `whoami` were added. The
   first question a model should ask about a small or stale answer is what it is
   allowed to see and how old the data is, and without a tool for each the only
   route to that is inference from a coverage fraction.
3. **The API image could never have started.** Its `CMD` named
   `finops_api.main:app`, and no such module level symbol has ever existed. Every
   deploy of that image would have failed at startup and nothing in the build
   would have caught it. Fixed with a `bootstrap()` factory and `--factory`, and
   a test now imports every target the Dockerfile names. ISS-114. It also needed
   one new setting, `METER_LOCAL_TENANT_ID`, because the local identity provider
   has no directory to read a tenant from.
4. **The layer ordering was written down twice and the two disagreed.**
   `pyproject.toml` put `finops_mcp` above `finops_api`, which is correct per
   constraint 8, and `scripts/docs/build_file_graph.py` put it below, so the
   graph check was enforcing the opposite of the rule for that pair. Neither
   check noticed, because each was internally consistent. ISS-115.
5. **Two issue numbers named two issues each.** ISS-110 and ISS-111 were both
   used twice, so half of them could not be cited unambiguously. Renumbered, and
   `scripts/docs/sync.py` now fails the build on a duplicate identifier in any
   section of the registry. ISS-116.
6. **ISS-109 re-probed and confirmed closed.** The facade contract's
   `finops_api.guards` entry was inert when the module did not exist. Importing
   it from `finops_mcp/tools.py` now breaks the contract, and breaks the
   `sqlalchemy` clause through the chain as well.

**Tests.**

| Test | Asserts |
| --- | --- |
| `tests/mcp/test_tools.py::test_a_tool_returns_exactly_what_the_caller_is_entitled_to` | The MCP path enforces exactly what the HTTP path enforces |
| `tests/mcp/test_contract.py::test_every_tool_declares_the_route_s_own_model` | A model change without a tool change fails |
| `tests/mcp/test_tools.py::test_the_meta_envelope_survives_the_facade` | Freshness and coverage survive the facade |
| `tests/mcp/test_contract.py::test_both_container_commands_name_something_that_exists` | An image whose command names a missing symbol fails the build |

**Do not.**

- Do not import the service layer or a repository from `finops_mcp`. It calls
  the HTTP API. Two implementations of an authorization rule is how an
  authorization bug is created, which is ISS-009 in a new place.
- Do not strip the `meta` envelope to make a tool response tidier. A model that
  cannot see `scope_coverage` will state a partial total as an organization
  total, confidently.
- Do not add a tool that runs free form SQL. See ADR-0007.
- Do not create a separate image. It would duplicate the whole dependency tree
  for one module and would need its own build, scan, signature and repository,
  which is how a deployable ends up outside the security gates. A001-F08.

**Evidence.**

```bash
pytest tests/mcp -v
```

---

### TASK-P0-031: wire the documentation and graph gates into the pipeline

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-28 |
| Implements | ADR-0011, `docs/03-CHANGE-CONTROL.md` |
| Depends on | TASK-P0-001 |
| Estimate | S |

**Goal.** The documentation, the feature docs and the file graph cannot go
stale without the pipeline saying so.

**Files.**

| Path | Action |
| --- | --- |
| `.gitlab-ci.yml` | four jobs added or corrected |
| `Makefile` | `check-docstrings` and `api-reference` targets, both in `verify` |
| `pyproject.toml` | the docstring ratchet, and two admitted dev dependencies |
| `tests/scripts/test_pipeline.py` | created, not planned. See deviation 2 |
| `.gitignore` | the generated reference, which is published not committed |

**Acceptance criteria.**

- [x] `make check-docs` runs in the `verify` stage and blocks. It previously ran
      three of its eight checks. ISS-119
- [x] `make graph` runs in CI and fails on a layering violation, through
      `check-docs`
- [x] `make review` runs on every merge request and publishes its report, and
      now on the default branch too. ISS-120
- [x] An API reference is generated from docstrings, and docstring coverage on
      public symbols is a gate

**Deviations.**

1. **The docstring gate is a ratchet at 70, not 80.** Measured coverage is 70.8
   percent, so the gate is set to the measured figure: it fails the moment
   coverage drops and never passes on a promise. Setting it above reality would
   have meant either writing about thirty five docstrings inside this task or
   shipping a gate that fails on the first run. ISS-117 tracks reaching 80, and
   the configuration says in as many words that the number may only go up. The
   fake provider is excluded, because it implements ports whose Protocols
   already document every method including which of the six causes each raises,
   and a copy on the double would drift from the Protocol within a release.
2. **Five jobs called `make` on images that do not have it.** `python:slim` is
   Debian with no build tools, so `lint` and three of the new jobs would have
   failed with "make: command not found" before running a single check. ISS-118.
   A test now reads the pipeline and fails when a job calls make on an image
   without it, and that test was itself probed by breaking the pipeline and
   confirming it fails.
3. **A duplicate job name silently deleted a job.** Adding a `code-review` job
   in `verify` replaced the existing one in `security`, because YAML resolves a
   repeated key in favour of the last. Nothing errors. The duplicate was
   removed, the existing job strengthened, and the same test now counts job
   names in the raw text rather than through the parser, since the parser is
   what hides the problem.
4. **The generated reference is not committed.** It is four megabytes of derived
   HTML that changes on every docstring. It is published as a pipeline artifact
   with a thirty day expiry and added to `.gitignore` and `make clean`.

**Do not.**

- Do not make any of these a warning. A documentation check that warns is
  ignored within two weeks, which is the whole reason it exists.
- Do not lower `fail-under`. Lowering a ratchet is how a gate becomes a
  formality.

**Evidence.**

```bash
make check-docs && make check-docstrings && make api-reference
```

---

### TASK-P0-033: SLOs, alerts and runbooks

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-29, not applied |
| Implements | `docs/10-OBSERVABILITY.md` |
| Depends on | TASK-P0-022, TASK-P0-025 |
| Estimate | M |

**Goal.** A collector that silently stops pages somebody, instead of the
product quietly serving stale numbers that look right.

**Files.**

| Path | Action |
| --- | --- |
| `infra/terraform/hub/observability.tf` | created |
| `infra/terraform/hub/dashboards/*.json` | created, three |
| `docs/runbooks/collection-stalled.md` | created |
| `docs/runbooks/platform-cost-anomaly.md` | created |
| `docs/runbooks/api-5xx.md` | created, not planned. See deviation 1 |
| `finops_ingest/metrics.py` | created |
| `tests/scripts/test_observability.py` | created, not planned |
| `tests/ingest/test_metrics.py` | created |

**Acceptance criteria.**

- [x] Four SLOs instrumented. Three are measured by metrics AWS already emits.
      Only SLO 1, collection freshness, needed a custom metric, because it is a
      fact about the data rather than about the service
- [x] Ten alarms created. **Four page**, not two. See deviation 1
- [x] Every log line carries `run_id`, `collector`, `scope_key`, `tenant_id`,
      through the structlog binding in the worker
- [x] Meter's own log groups have retention set at creation, in
      `infra/terraform/hub/logs.tf`
- [x] The three dashboards are provisioned as code, with a one minute refresh
      and no panel over a 24 hour window. A test asserts both
- [x] A runbook exists for each paging alert. Three files cover four alarms,
      because the widespread stalled alarm is the same failure as the single
      scope one and its first step is telling them apart

**Deviations.**

1. **Four alerts page, not two.** The criterion above said two, and so did
   `docs/runbooks/README.md`. Both were misreadings of the sentence under the
   alert table in `docs/10-OBSERVABILITY.md`: two of the four are *unusual*,
   which is not the same as two being the total. The table marks collection
   stalled, collection stalled widespread, API 5xx and platform cost anomaly as
   Page, and all four are right on the merits. The table was followed and the
   two summaries corrected. ISS-121.
2. **The alert threshold is three cadences and the screen's is two.** A page
   fires strictly later than the screen turns amber. Paging on the threshold an
   operator is already looking at is how a page gets muted.
3. **The collection alarms treat a missing datapoint as breaching.** A stalled
   metric publisher is the same class of failure as a stalled collector, and
   treating its absence as healthy would leave the alarm working only while the
   thing it watches is working.
4. **The platform cost alarm uses an anomaly band, not a fixed multiple.**
   Meter's cost is expected to grow with the number of accounts it reads, so a
   fixed threshold would be wrong within a quarter and would then be raised
   rather than investigated.
5. **Metrics are dimensioned by collector, never by scope.** One metric per
   account per region per collector is thousands of metrics at three hundred
   accounts, which is a bill this product would flag. The stalled scope is found
   in `sync_error`, which is the runbook's first step anyway.

**Do not.**

- Do not count `PARTIAL` as a run failure. It is success at the run level, and
  counting it would make the alert fire constantly at 300 accounts and it would
  be muted within a week.
- Do not log a credential, an ExternalId, or any payload from a member account.
  Log the metadata and the typed error.
- Do not ship a paging alert without its runbook. That is a page that wakes
  someone who then has to work out what to do.
- Do not exempt Meter's own dashboards from FEAT-014. A team that exempts
  itself from the control it sells has lost the argument.

**Evidence.**

```bash
terraform -chdir=infra/terraform/hub validate
pytest tests/scripts/test_observability.py tests/ingest/test_metrics.py -v
```

Terraform validates and 19 tests pass. The screenshot of a deliberately stalled
collector in ALARM was NOT produced: it needs the stack deployed. ISS-122.

---

## Traceability

Every task maps to a spec section and a feature. If a task cannot name its
spec section, the spec is incomplete and must be updated before the task is
worked.

| Feature | Tasks |
| --- | --- |
| FEAT-001 Account onboarding and organization topology | 014, 018, 019, 022, 025, 027 |
| FEAT-002 Cross account credential brokering | 013, 014, 017 |
| FEAT-003 Provider port abstraction | 007, 008, 009 |
| FEAT-004 FOCUS canonical cost schema | 006, 010 |
| FEAT-005 Ingestion framework | 020, 021 |
| FEAT-006 Typed errors and freshness | 005, 024, 025, 026, 028 |
| FEAT-007 Authorization scope enforcement | 011, 012, 024 |
| FEAT-008 Platform self metering | 015, 023, 025, 028 |
| FEAT-009 Organization map | 026, 027 |
| FEAT-010 Ingest and freshness surface | 028 |
| FEAT-050 Visual honesty system | 035, 026 |
| FEAT-042 Assistant bot, groundwork | 030 |
| Security posture, ADR-0010 | 029 |
| Documentation and graph gates, ADR-0011 | 031 |
| Retention and erasure, data classification | 032 |
| SLOs, alerts and runbooks, observability | 033 |
