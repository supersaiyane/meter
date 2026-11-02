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
| Status | Not started |
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

- [ ] `npm ci && npm run build` produces `finops-web/dist`
- [ ] `npm run lint` and `npm run test -- --run` pass
- [ ] `package.json` defines `format`, `lint`, `test` and `build`, because the
      Makefile calls all four

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
| Status | Not started |
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

- [ ] Fails with a clear message when `INDEX.md` links a missing path
- [ ] Fails when a file under `docs/` is not linked from `INDEX.md`
- [ ] Passes on the repository as it stands
- [ ] Exit code is 1 on failure, so CI actually stops

**Do not.**

- Do not make it a warning. A documentation check that warns is a check that is
  ignored within two weeks.

**Evidence.**

```bash
make check-docs
```

---

### TASK-P0-004: add the CI pipeline gate and pre commit configuration

| Field | Value |
| --- | --- |
| Status | Not started |
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

- [ ] Pipeline stages `verify` all pass on the scaffold
- [ ] A commit containing an em dash is rejected locally by pre commit
- [ ] `terraform-validate` is allowed to fail only until TASK-P0-013 lands, and
      the allowance is removed in that task

**Do not.**

- Do not skip the writing rules job to unblock a pipeline. Fix the text.

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
| Status | Not started |
| Implements | P0 spec section 10, ADR-0004 |
| Delivers | FEAT-002 |
| Depends on | none |
| Estimate | S |

**Goal.** `FinOpsOrgReaderRole` in the management account, trusted only by the
hub role.

**Files.**

| Path | Action |
| --- | --- |
| `infra/terraform/management/main.tf` | create |
| `infra/terraform/management/variables.tf` | create |
| `infra/terraform/management/outputs.tf` | create |
| `infra/terraform/management/envs/dev.tfvars` | create |

**Acceptance criteria.**

- [ ] Grants only `organizations:List*` and `organizations:Describe*`
- [ ] Trust policy requires the hub role principal and an ExternalId
- [ ] `terraform validate` and `terraform fmt -check` pass
- [ ] The `terraform-validate` allowance added in TASK-P0-004 is removed here

**Do not.**

- Do not grant `organizations:*`. Write access to the organization from a
  reporting tool will not survive a security review, and correctly so.

**Evidence.**

```bash
terraform -chdir=infra/terraform/management validate && terraform -chdir=infra/terraform/management fmt -check
```

---

### TASK-P0-014: Terraform for the member account StackSet

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P0 spec section 10, ADR-0004 |
| Delivers | FEAT-001, FEAT-002 |
| Depends on | TASK-P0-013 |
| Estimate | M |

**Goal.** `FinOpsCollectorRole` deployed to every account automatically, so a
newly vended account onboards with no human step.

**Files.**

| Path | Action |
| --- | --- |
| `infra/terraform/member/main.tf` | create |
| `infra/terraform/member/collector_role.yaml` | create |
| `infra/terraform/member/variables.tf` | create |
| `infra/terraform/member/envs/dev.tfvars` | create |

**Acceptance criteria.**

- [ ] Service managed StackSet with `auto_deployment` enabled against the
      organization root
- [ ] Trust policy requires the hub role, an ExternalId, and an
      `aws:PrincipalOrgID` condition
- [ ] The policy is a curated action list, and `ReadOnlyAccess` appears nowhere
- [ ] The action list is a single documented block, each action annotated with
      the collector that needs it

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

---

### TASK-P0-015: Terraform for the hub network and data layer

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P0 spec section 10 |
| Depends on | none |
| Estimate | L |

**Goal.** VPC, endpoints, Aurora, SQS, S3 and Secrets Manager.

**Files.**

| Path | Action |
| --- | --- |
| `infra/terraform/hub/network.tf` | create |
| `infra/terraform/hub/database.tf` | create |
| `infra/terraform/hub/queue.tf` | create |
| `infra/terraform/hub/storage.tf` | create |
| `infra/terraform/hub/variables.tf` | create |
| `infra/terraform/hub/envs/dev.tfvars` | create |
| `infra/terraform/hub/envs/dev.backend.hcl` | create |

**Acceptance criteria.**

- [ ] Private subnets with interface endpoints for STS, SQS, Secrets Manager,
      Cost Explorer and CloudWatch Logs, plus a gateway endpoint for S3
- [ ] No NAT Gateway, per the reasoning in `docs/04-DEPLOYMENT.md`
- [ ] Aurora Serverless v2, encrypted, not publicly accessible
- [ ] SQS main queue with a dead letter queue after 3 receives
- [ ] Every resource carries a `finops:module` tag, which is what makes
      FEAT-008 work

**Do not.**

- Do not add a NAT Gateway "just in case". If a collector needs the public
  internet, that is a design question to answer, not a default to pay for.
- Do not make the database publicly accessible for convenience during
  development. Use the compose stack for that.
- Do not forget the `finops:module` tag. Self metering silently reports nothing
  rather than failing, which is the worst kind of broken.

**Evidence.**

```bash
make tf-init && make tf-plan
```

---

### TASK-P0-016: Terraform for ECS, ALB and ECR

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P0 spec section 10, `docs/04-DEPLOYMENT.md` |
| Depends on | TASK-P0-015 |
| Estimate | L |

**Goal.** The three services run on Fargate behind an ALB, with `image_tag` as
a variable so Terraform owns the deploy.

**Files.**

| Path | Action |
| --- | --- |
| `infra/terraform/hub/ecr.tf` | create |
| `infra/terraform/hub/ecs.tf` | create |
| `infra/terraform/hub/alb.tf` | create |
| `infra/terraform/hub/iam.tf` | create |
| `infra/terraform/hub/scheduler.tf` | create |

**Acceptance criteria.**

- [ ] Four ECR repositories: api, worker, web, cache, with lifecycle policies.
      **No mcp repository**: the MCP server is a second process in the api
      image, see ADR-0009
- [ ] ECR tag mutability set to `IMMUTABLE`, so a tag cannot be repointed at a
      different image after it was scanned and signed. ISS-054
- [ ] ECR enhanced scanning enabled on every repository
- [ ] A second ECS service running the api image with the command overridden to
      `finops_mcp.server`
- [ ] Task definitions take `image_tag` as a variable, per `docs/04-DEPLOYMENT.md`
- [ ] `FinOpsHubTaskRole` can assume only `role/FinOpsCollectorRole` in any
      account, restricted by `aws:PrincipalOrgID`
- [ ] Worker service scales on `ApproximateNumberOfMessagesVisible`
- [ ] EventBridge Scheduler triggers the dispatcher hourly
- [ ] ALB health check targets `/healthz` and the rollout waits for stable

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
make tf-plan
```

---

## Wave E: AWS adapters

### TASK-P0-017: implement the AWS credential broker

| Field | Value |
| --- | --- |
| Status | Not started |
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

- [ ] Assumes `FinOpsCollectorRole` with the ExternalId from Secrets Manager
- [ ] Caches sessions until 5 minutes before expiry, then refreshes
- [ ] Maps `AccessDenied` and `AccessDeniedException` to the `AccessDenied`
      domain error, and throttling codes to `Throttled`
- [ ] Sets connect and read timeouts, and a bounded retry policy, so a broken
      network path fails fast rather than consuming the whole task timeout
- [ ] Passes the contract suite from TASK-P0-009 under `moto`

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
| Status | Not started |
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

- [ ] Walks `ListRoots`, then `ListOrganizationalUnitsForParent` and
      `ListAccountsForParent` recursively
- [ ] Paginates everything. No unpaginated call anywhere
- [ ] Returns domain `OrgNode` and `CloudAccount`, never a raw API shape
- [ ] Handles a suspended account without failing the run
- [ ] Backs off on throttling rather than failing, per the P0 risk table

**Tests.**

| Test | Asserts |
| --- | --- |
| `tests/providers/aws/test_accounts.py::test_builds_four_level_tree` | Nested organizational units resolve with correct parents |
| `tests/providers/aws/test_accounts.py::test_paginates` | A 300 account fixture returns 300, not the first page |
| `tests/providers/aws/test_accounts.py::test_suspended_account_is_marked_not_dropped` | A suspended account appears with the correct status |

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
| Status | Not started |
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

- [ ] Attempts an assume role plus one cheap call
- [ ] Maps the outcome to `HEALTHY`, `ACCESS_DENIED`, `NOT_DEPLOYED`,
      `THROTTLED` or `UNKNOWN`
- [ ] Distinguishes "role does not exist" from "role exists but denies", since
      the remediation differs completely
- [ ] Records the error string, so a user can act without reading logs

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
| Status | Not started |
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

- [ ] Claims a run by inserting the idempotency key, and a duplicate claim is a
      no operation rather than a second run
- [ ] Records `items_written`, `bytes_read`, `error_type` and the as of window
- [ ] Advances the watermark only on success
- [ ] A crashed run is reclaimable after a timeout, rather than blocking that
      scope forever

**Tests.**

| Test | Asserts |
| --- | --- |
| `tests/ingest/test_ledger.py::test_running_three_times_writes_one_result_set` | The core idempotency guarantee, ISS-008 |
| `tests/ingest/test_ledger.py::test_watermark_not_advanced_on_failure` | A failed run does not skip data |
| `tests/ingest/test_ledger.py::test_crashed_run_is_reclaimable` | A stale claim can be retaken |

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
| Status | Not started |
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

- [ ] Dispatcher enumerates `(tenant, account, region, collector)` and publishes
      one message per unit, with a dedup key
- [ ] Worker claims a run, resolves credentials, executes, records the outcome
- [ ] A raised domain error is recorded against that scope and the worker
      continues. It never propagates to fail the batch
- [ ] Messages failing three times land in the dead letter queue
- [ ] Structured logs carry `run_id`, `collector`, `scope_key` on every line

**Tests.**

| Test | Asserts |
| --- | --- |
| `tests/ingest/test_worker.py::test_one_account_access_denied_does_not_fail_run` | Spec section 11, test 1. The single most important test in P0 |
| `tests/ingest/test_worker.py::test_no_data_and_access_denied_are_distinguishable` | Spec section 11, test 2. ISS-015 |
| `tests/ingest/test_dispatcher.py::test_dedup_key_prevents_duplicate_units` | Re dispatch within a window is a no operation |

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
| Status | Not started |
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

- [ ] Rebuilds `org_node` transactionally, so the tree is never half updated
- [ ] Upserts `cloud_account`, and marks a departed account as such rather than
      deleting it
- [ ] A new account appears within one hour with no human step, which is the
      P0 definition of done
- [ ] `role_health` is set for every account on every run

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
| Status | Not started |
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

- [ ] One daily Cost Explorer request, grouped by the `finops:module` tag
- [ ] Runs daily, not hourly, because Cost Explorer charges per request
- [ ] An untagged cost lands in an explicit `unallocated` bucket rather than
      being dropped
- [ ] The Cost Explorer request cost is itself attributed to the ingest module

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
| Status | Not started |
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

- [ ] Every response carries `meta` with `as_of`, `scope_coverage` and
      `degraded`
- [ ] `/healthz` reports database reachability and ingestion freshness, not
      just process liveness
- [ ] A route registered without the scope dependency still cannot return out
      of scope rows, because the repository guard catches it

**Tests.**

| Test | Asserts |
| --- | --- |
| `tests/api/test_scope_enforcement.py::test_route_without_dependency_cannot_leak` | Spec section 11. The adversarial test for ISS-009 |
| `tests/api/test_scope_enforcement.py::test_every_response_carries_meta` | Iterates the registered routes and asserts the envelope |

**Also.** `finops_api.guards` now exists, so the last inert target in the
`finops_mcp` contract becomes live. Confirm it fires by probe, as in
TASK-P0-011. ISS-109 closes here.

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
| Status | Not started |
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

- [ ] All seven routes from spec section 8 exist and match the documented shape
- [ ] `/org/tree` marks branches outside scope as unreachable rather than
      hiding them, so the tree shape stays honest
- [ ] `/ingest/runs` returns typed errors with their remediation text
- [ ] `/health/freshness` reports staleness per collector and scope

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
| Status | Not started |
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

- [ ] **`Figure` cannot render without provenance and freshness.** They are
      required props, and the type system rejects a call without them
- [ ] Provenance is encoded three times: fill, `~` prefix, and text label.
      A test asserts the label is present with colour disabled
- [ ] `measured` renders solid, `modelled` renders hatched, `forecast` renders
      hatched with an interval and **never as a single number**
- [ ] `Figure` given a typed error renders the cause and its remediation, and
      **renders no numeral at all**
- [ ] `NoData` is the only cause that renders as `0`
- [ ] `StateBoundary` implements all seven states from design system section 8
- [ ] All numerals tabular, right aligned, fixed decimal places including
      trailing zeros
- [ ] `DataTable` virtualises past 200 rows
- [ ] Tokens defined for light and dark, both first class
- [ ] Axe reports zero violations on every component
- [ ] Reduced motion respected

**Tests.**

| Test | Asserts |
| --- | --- |
| `Figure.test.tsx::renders_no_numeral_for_a_failure` | The rule the whole design exists to protect |
| `Figure.test.tsx::nodata_renders_zero` | And that the one legitimate zero still works |
| `Figure.test.tsx::provenance_survives_without_colour` | Fill and label carry it independently |
| `Figure.test.tsx::forecast_renders_an_interval` | ADR-0015 condition 2 as a rendering rule |
| `StateBoundary.test.tsx::implements_seven_states` | Not three |

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
| Status | Not started |
| Implements | P0 spec section 9, screen 1 |
| Delivers | FEAT-006, FEAT-009, FEAT-050 |
| Depends on | TASK-P0-025, TASK-P0-035 |
| Estimate | M |

**Files.** `finops-web/src/` shell, layout, navigation, API client, and the
`meta` envelope handling. Uses the components from TASK-P0-035, and adds none.

**Acceptance criteria.**

- [ ] A persistent banner reads "showing N of M accounts" whenever coverage is
      partial, per ISS-016
- [ ] A global freshness indicator shows the oldest `as_of` in view
- [ ] A degraded response is visually distinct from a healthy one

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
| Status | Not started |
| Implements | P0 spec section 9, screens 2 and 3 |
| Delivers | FEAT-001, FEAT-009 |
| Depends on | TASK-P0-026 |
| Estimate | L |

**Acceptance criteria.**

- [ ] Accounts table filters by role health, so broken onboarding is one click
- [ ] Tree view is the default, and is keyboard navigable
- [ ] Graph view renders with Cytoscape.js and stays usable at 300 accounts
- [ ] Unreachable branches are drawn, marked, and not clickable

**Do not.**

- Do not make the graph the default view. At 300 accounts a force directed
  graph is slower to read than a tree, and it is the first thing a user opens.
- Do not render more than 2,000 nodes. Filter server side.

**Evidence.** `npm run test -- --run`, plus a screenshot at 300 accounts.

---

### TASK-P0-028: ingest, freshness and platform cost screens, plus the end to end journey

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P0 spec section 9, screens 4 and 5 |
| Delivers | FEAT-006, FEAT-008, FEAT-010 |
| Depends on | TASK-P0-027 |
| Estimate | M |

**Acceptance criteria.**

- [ ] Ingest screen shows per collector and per scope status with typed errors
      and remediation text
- [ ] A failed collection is visually distinct from a zero result, per ISS-015
- [ ] Platform cost screen shows spend by module with a 30 day sparkline
- [ ] A Playwright journey covers login through to the organization map
- [ ] P0 definition of done is demonstrable end to end
- [ ] **Performance budgets 1 and 2 asserted**, see spec section 11b: a 300
      account sweep under 15 minutes against a seeded fake provider, and API
      p95 under 500 ms on scoped reads
- [ ] **Restore drill performed**: restore Aurora into a scratch database, run
      the migrations, confirm the application starts and the freshness screen
      reports correctly. A restore that has never been tested is a hypothesis

**Do not.**

- Do not render a failed collection as a zero, a dash, or an empty cell. It
  gets read as "no cost", which is the specific failure ISS-015 exists to
  prevent, and it is the last chance to catch it.

**Evidence.**

```bash
make test-all && make test-e2e
```

---

### TASK-P0-032: retention jobs and the erasure script

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | `docs/09-DATA-CLASSIFICATION.md` |
| Depends on | TASK-P0-021 |
| Estimate | M |

**Goal.** Retention is enforced by a job, not stated as a policy nobody runs.

**Files.**

| Path | Action |
| --- | --- |
| `finops_ingest/collectors/retention.py` | create |
| `scripts/ops/erase_principal.py` | create |
| `tests/ingest/collectors/test_retention.py` | create |

**Acceptance criteria.**

- [ ] Five jobs: `retention_principal`, `retention_operational`,
      `retention_audit`, `retention_cost`, `retention_scope_cache`
- [ ] Each writes an `ingest_run`, so a stopped retention job appears on the
      freshness screen exactly like a stopped collector
- [ ] `retention_principal` anonymises rather than removing rows, so audit
      joins do not dangle
- [ ] `erase_principal.py` performs all five erasure steps in one transaction
      and prints what it changed
- [ ] Backup retention set in Terraform to match the table policy

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
| Status | Not started |
| Implements | P0 spec section 8.0, ADR-0009 |
| Delivers | FEAT-042 groundwork |
| Depends on | TASK-P0-025 |
| Estimate | M |

**Goal.** An MCP server exposing the P0 read surface, proving the facade
pattern before there is much to expose.

**Files.**

| Path | Action |
| --- | --- |
| `finops_mcp/__init__.py` | create |
| `finops_mcp/server.py` | create |
| `finops_mcp/tools.py` | create |
| `tests/mcp/test_tools.py` | create |

**Acceptance criteria.**

- [ ] Ships as a second process in the `meter-api` image, selected by the
      container command. No fourth image, see ADR-0009
- [ ] Four tools: `list_accounts`, `get_org_tree`, `get_ingest_status`,
      `get_platform_cost`
- [ ] Every tool calls the HTTP API over the network with the caller's token
- [ ] Tool schemas are generated from the same Pydantic models the API uses,
      so a drift between the two surfaces fails the build
- [ ] Every tool response carries the `meta` envelope unchanged, including
      `scope_coverage`, so a model cannot present a partial total as complete
- [ ] A caller with a two account scope receives two accounts from the tool

**Tests.**

| Test | Asserts |
| --- | --- |
| `tests/mcp/test_tools.py::test_tool_respects_scope` | The MCP path enforces exactly what the HTTP path enforces |
| `tests/mcp/test_tools.py::test_schemas_match_api_models` | A model change without a tool change fails |
| `tests/mcp/test_tools.py::test_meta_envelope_is_preserved` | Freshness and coverage survive the facade |

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
| Status | Not started |
| Implements | ADR-0011, `docs/03-CHANGE-CONTROL.md` |
| Depends on | TASK-P0-001 |
| Estimate | S |

**Goal.** The documentation, the feature docs and the file graph cannot go
stale without the pipeline saying so.

**Acceptance criteria.**

- [ ] `make check-docs` runs in the `verify` stage and blocks
- [ ] `make graph` runs in CI and fails on a layering violation
- [ ] `make review` runs on every merge request and publishes its report
- [ ] An API reference is generated from docstrings, and docstring coverage on
      public symbols is a gate

**Do not.**

- Do not make any of these a warning. A documentation check that warns is
  ignored within two weeks, which is the whole reason it exists.

**Evidence.**

```bash
make check-docs && make graph && make review
```

---

### TASK-P0-033: SLOs, alerts and runbooks

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | `docs/10-OBSERVABILITY.md` |
| Depends on | TASK-P0-022, TASK-P0-025 |
| Estimate | M |

**Goal.** A collector that silently stops pages somebody, instead of the
product quietly serving stale numbers that look right.

**Files.**

| Path | Action |
| --- | --- |
| `infra/terraform/hub/observability.tf` | create |
| `infra/terraform/hub/dashboards/*.json` | create |
| `docs/runbooks/collection-stalled.md` | create |
| `docs/runbooks/platform-cost-anomaly.md` | create |
| `finops_ingest/metrics.py` | create |

**Acceptance criteria.**

- [ ] Four SLOs instrumented, per `docs/10-OBSERVABILITY.md`
- [ ] Ten alarms created, of which exactly two page: collection stalled, and
      platform cost anomaly
- [ ] Every log line carries `run_id`, `collector`, `scope_key`, `tenant_id`
- [ ] **Meter's own log groups have retention set at creation**, in Terraform
- [ ] The three dashboards are provisioned as code, with
      `min_refresh_interval` at 1 minute and no Logs Insights panel over a
      window longer than 24 hours
- [ ] A runbook exists for each of the two paging alerts

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
make tf-plan
```

Plus a screenshot of the collection health dashboard with a deliberately
stalled collector, showing the alarm in ALARM state.

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
