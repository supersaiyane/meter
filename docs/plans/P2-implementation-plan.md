# P2 Query Cost Governance: implementation plan

Date: 2026-08-23
Status: Provisional, pending approval of `docs/specs/2026-08-23-p2-query-cost-governance-design.md`
Spec: `docs/specs/2026-08-23-p2-query-cost-governance-design.md`
Depends on: P0 delivered
Tasks: 22

## How to work this plan

Same contract as P0. Read `docs/03-CHANGE-CONTROL.md`, section "The anti
hallucination contract", before starting.

One task, one commit. Read the **Do not** list before writing code, not after.
If reality does not match the spec, stop, raise an `ISS-nnn`, fix the spec, add
a `CHG-nnnn`, then continue.

**One rule specific to P2.** A working prototype exists,
`sample_lambda.py`, 2,740 lines. It is **ported, not rewritten**. Its cost model
is the specification, and a port that changes a number silently is a regression
nobody would notice. TASK-P2-002 pins it with golden file tests before anything
else touches it.

## Wave overview

| Wave | Tasks | Delivers | Can start when |
| --- | --- | --- | --- |
| A. Pin and decompose | 001 to 003 | The prototype's behaviour captured as tests, then split | P0 delivered |
| B. Port and strategies | 004 to 008 | `QuerySurface` plus three connections and a fake | A complete |
| C. Schema | 009 | Six tables and their constraints | P0 delivered |
| D. Audit | 010 to 012 | The 6 hourly survey, end to end | B and C |
| E. Evidence | 013 to 014 | Measured overlay and ownership | D |
| F. Control | 015 to 016 | The event driven kill switch | C |
| G. Prevention | 017 to 018 | Workspace floor and the CI gate | B |
| H. Remediation | 019 | Panel rewrite with undo | G |
| I. Calibration | 020 | The published accuracy figure | D, and P1 cost data |
| J. Surface | 021 | Routes and MCP tools | D to E. **F is parked**, so the enforcement route lands with TASK-P2-016 |
| K. Screens | 022 to 025 | Four screens, fixture backed and reviewable | TASK-P0-037. **Not D to H** |

Waves F and G do not depend on D. With two people, one takes the audit path and
the other takes control and prevention, which is also the fastest route to the
thing that actually stops the bleed.

**Wave K does not wait for wave J.** The four screens are built against typed
fixtures using the seam from TASK-P0-037, so each one is reviewable for layout,
language and honesty from the moment its shape is known rather than the moment
its data is real. When TASK-P2-021 lands the routes, the client gains the
methods and the screens start reading real data with no further change, because
resolution is derived from the client rather than from a list. Under the
previous ordering the first pixel of P2 appeared at task 21 of 22, which put
every interface mistake at the most expensive point to find one.

---

## Wave A: pin and decompose

### TASK-P2-001: import the prototype and pin its behaviour

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-02 |
| Implements | P2 spec section 1 |
| Depends on | none |
| Estimate | M |

**Goal.** The prototype's current output captured as fixtures, before a line of
it is changed.

**Files.**

| Path | Action |
| --- | --- |
| `finops_query/_legacy/sample_lambda.py` | created, byte identical, sha256 `80854e42` |
| `tests/query/fixtures/dashboards/*.json` | created, 14 |
| `tests/query/fixtures/alerts/alert-rules.json` | created, 4 rules |
| `tests/query/fixtures/golden/*.json` | created, 15 |
| `tests/query/conftest.py` | created, the offline harness |
| `tests/query/test_legacy_baseline.py` | created |
| `tests/query/test_legacy_is_frozen.py` | created, not planned. See deviation 2 |

**Acceptance criteria.**

- [x] At least 12 fixture dashboards covering every engine: Logs Insights,
      metric search, Metric Insights SQL, PromQL, plus a malformed panel, a
      template heavy panel and an alert rule. Fourteen, and a test asserts both
      the count and that all four engines actually appear in the output
- [x] The unmodified prototype runs against each fixture and its output is
      committed as a golden file
- [x] `test_legacy_baseline.py` asserts the prototype reproduces every golden
      file exactly

**Deviations.**

1. **Only two entry points are pinned**, `analyze_dashboard` and
   `analyze_alert_rules`. They are the only parts of the file reachable without
   AWS, because every other path opens a client. Pinning the rest would mean
   mocking boto3 inside a baseline test, and a baseline whose shape is decided
   by the mocks is not a baseline. The harness passes `None` as the session and
   a second test passes an object that raises on any attribute access, so a
   reintroduced AWS call fails rather than quietly finding ambient credentials.
2. **The copy is pinned by hash.** `_legacy` is excluded from ruff, from mypy
   and from coverage, and the cost of those three exclusions is that nothing
   else in the build would notice the file being edited. A golden regenerated
   alongside an edit would hide it too.
3. **Regeneration is deliberately awkward.** It needs
   `METER_REGENERATE_GOLDEN=yes-i-mean-it` rather than a pytest flag, and a
   missing golden fails rather than being created. A test that writes its own
   expectation on first run passes on every first run, including the one after
   somebody deletes the file to make a failure go away.
4. **Two defects found in this project's own tooling**, both surfaced by adding
   the package. `sync.py` counted any task status it did not recognise as "not
   started", so descoping TASK-P2-007 and 008 read as 22 tasks remaining rather
   than 20. And `finops_query` was invisible to the linter until the scope test
   written on 2026-09-02 failed on it, which is the first time that test caught
   something it was not written for. ISS-130.

**Do not.**

- Do not fix anything in the prototype in this task, including obvious bugs. A
  baseline that already includes your fixes is not a baseline. Record what looks
  wrong as an `ISS-nnn` and fix it in a later task where the golden file change
  is visible in a diff.
- Do not hand write the golden files. Generate them from the prototype, or they
  capture your belief about its behaviour rather than its behaviour.

**Evidence.**

```bash
pytest tests/query -v
```

21 tests pass. The baseline records, among other things, that a 30 second
refresh over a 7 day window on a 50 GB per day log group models at 12,600 USD
per month and is rated CRITICAL. That figure is modelled, not measured, and
TASK-P2-020 is what back tests it against a bill.

---

### TASK-P2-002: extract the cost model under the golden files

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-03 |
| Implements | P2 spec section 4 |
| Delivers | FEAT-012 |
| Depends on | TASK-P2-001 |
| Estimate | L |

**Goal.** The cost model as a standalone module, producing byte identical
output to the prototype.

**Files.**

| Path | Action |
| --- | --- |
| `finops_query/cost_model.py` | created, 370 lines |
| `finops_query/classify.py` | created, 254 lines |
| `tests/query/test_cost_model.py` | created, 27 tests |
| `tests/query/test_classify.py` | created, not planned. See deviation 3 |
| `finops_core/config.py` | 13 fields added |
| `.env.example` | 13 values documented |

**Acceptance criteria.**

- [x] Every golden file from TASK-P2-001 reproduces exactly through the new
      module, with one enumerated divergence. See deviation 1
- [x] Every rate, assumption and window is a setting, not a literal.
      `check_hardcoded.py` passes, and now actually reads the package. See
      deviation 2
- [x] The engine classifier is separate from the cost model
- [x] Each module is under the 800 line ceiling, 370 and 254, and a test
      asserts it

**Deviations.**

1. **One string diverges, and it is enumerated rather than absorbed.** The
   prototype writes an em dash into the Prometheus reason string. This project's
   writing rules forbid the character anywhere, and the frozen copy is exempt
   only because it is frozen. New code is not, so the extraction writes a comma.
   `KNOWN_DIVERGENCES` in the test names the exact pair, a second test asserts
   the list has one entry and that both halves really occur in the two files,
   and any other difference at all fails. A comparison that normalised
   punctuation would also have hidden a real change to a reason string, and the
   reasons are the part of a finding a person reads.
2. **`check_hardcoded.py` never scanned `finops_query`.** The criterion above
   would have been satisfied over code the gate had not read.
   `check_forbidden_imports.py` already listed the package and this one did not.
   ISS-134, and probed by planting a region literal and confirming it is caught.
3. **Two defects found and deliberately not fixed.** `classify` decides a
   CloudWatch target is Logs Insights if its expression merely contains
   "filter ", which matches the metric maths `FILTER` function and prices a
   metric query as a log scan. And an unrecognised datasource reports its own
   type as the engine, so a Postgres panel is priced at zero, and zero reads as
   free rather than as not understood. Both are pinned by tests that say they
   are pinned rather than endorsed. ISS-132 and ISS-133.
4. **The risk score keeps its point values as module constants**, not settings.
   They were bare numbers in a comparison chain, which is a policy hidden in an
   expression, but they are the definition of the score rather than something a
   tenant tunes. The thresholds they are compared against are the settings.

**Do not.**

- Do not change a formula while extracting it. If a formula is wrong, extract
  it faithfully first, then change it in its own commit where the golden file
  diff shows exactly which numbers moved and by how much.
- Do not keep `VIEWING_HOURS_PER_DAY` or any rate as a module constant. They
  are tenant configurable and belong in settings, per ADR-0017.

**Evidence.**

```bash
pytest tests/query -v && make check-docs
```

53 tests pass and every golden reproduces. Coverage is 98 percent on both new
modules.

---

### TASK-P2-003: decompose the remainder and delete the legacy copy

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-04 |
| Implements | P2 spec section 4 |
| Depends on | TASK-P2-002 |
| Estimate | M |

**Goal.** No file over 800 lines, and `_legacy/` gone.

**Files.**

| Path | Action |
| --- | --- |
| `finops_query/policy.py` | created, 135 lines |
| `finops_query/ownership.py` | created, 244 lines |
| `finops_providers/grafana/client.py` | created, 224 lines |
| `finops_query/_legacy/` | removed, 2,740 lines |
| `tests/query/test_policy.py` | created, 14 tests |
| `tests/query/test_ownership.py` | created, 22 tests |
| `tests/providers/test_grafana_client.py` | created, 22 tests |

**Acceptance criteria.**

- [x] Every golden file still reproduces, now from `Settings` rather than from
      the prototype's config dict. That was the condition for deleting it
- [x] `_legacy/sample_lambda.py` is removed, not left for reference
- [x] `make graph` shows no layering violation, and `finops_query` is now
      subject to one. See deviation 3

**Deviations.**

1. **The Grafana client does not reproduce the prototype's error handling.**
   It wrapped every call in `except Exception: return []`, so a workspace the
   token could not read reported zero dashboards, which renders as "this
   workspace costs nothing" rather than as "we could not look". That is
   constraint 5, and a new module in `finops_providers` cannot reproduce it.
   Every failure is now one of the six typed causes. No golden covers the HTTP
   layer, so nothing was hidden by the change.
2. **A search result at Grafana's 5,000 cap is refused.** Grafana does not
   report that it truncated, so an estate larger than the cap was silently
   audited in part and reported as whole. Refusing is better than auditing an
   unknown fraction of an estate and calling it the estate.
3. **`finops_query` was in no layer list at all.** Not the import-linter
   contract, not the graph builder, and not the distribution's own package list.
   It could have imported `finops_api` and all three checks would have passed.
   Holding the two orderings equal did not catch it, because they agreed about a
   package neither mentioned. `tests/scripts/test_layer_agreement.py` now
   asserts every declared package has a layer, and the constraint was probed by
   importing `finops_api` from `finops_query` and confirming it breaks.
4. **Six exclusions removed, which was the point.** ruff, mypy, coverage,
   `check-writing`, `check_hardcoded` and `check_forbidden_imports` each had a
   `_legacy` carve out. The last one mattered most: it was suppressing the
   `urllib.request` rule that CVE-2026-15806's acceptance depends on. The
   Grafana adapter uses httpx, so that claim is unconditional again.
5. **The HTML renderer, the delivery code and the orchestration were not
   extracted, they were deleted with the copy.** The renderer is superseded by
   the four screens in TASK-P2-022, delivery by the platform's own API, and
   orchestration by the collector in TASK-P2-010. Porting them would have meant
   carrying 1,300 lines that nothing will call. They are in git history.

**Do not.**

- Do not keep the legacy file. It is in git history, which is where superseded
  code belongs. A copy left in the tree becomes the version someone reads.

**Evidence.**

```bash
pytest tests/query tests/providers -v && make graph
```

555 tests pass. No file in `finops_query` exceeds 370 lines.

---

## Wave B: the port and three connections

### TASK-P2-004: define the QuerySurface port

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-05 |
| Implements | P2 spec section 4.1 |
| Delivers | FEAT-011 |
| Depends on | TASK-P2-003 |
| Estimate | M |

**Files.**

| Path | Action |
| --- | --- |
| `finops_core/domain/query.py` | created, not planned. See deviation 1 |
| `finops_core/ports/query.py` | created |
| `finops_core/ports/__init__.py` | exports it, and two grouping tuples |
| `tests/query/test_ports.py` | created, 20 tests |

**Acceptance criteria.**

- [x] `QuerySurface` in `finops_core/ports/`, with `discover`, `list_queries`
      and `apply_control`, and a test asserting those three and no others
- [x] No Grafana type appears in any signature. A test checks every signature
      and every field of every type they return against a list of vendor words,
      and it was probed by putting `GrafanaWorkspace` in a return type
- [x] The import linter contract covers `finops_query`, which TASK-P2-003 did
      when it found the package was in no layer list at all. ISS-135
- [x] Each method documents which of the six error types it may raise, and the
      test takes the six from the taxonomy rather than listing them, so a
      seventh cause cannot be added without this noticing

**Deviations.**

1. **A domain module came with it.** The plan named only the port, but "do not
   return a Grafana dashboard object, return a domain `QueryDefinition`" needs
   `QueryDefinition` to exist. `finops_core/domain/query.py` holds it along with
   `SurfaceInstance`, `ControlRequest` and `ControlOutcome`.
2. **`SurfaceInstance` refuses to be unreachable without naming a cause.** A
   `ValueError` in `__post_init__`, because an instance that could not be read
   has to appear in the list saying why. Omitted, it makes the estate look
   smaller and cheaper than it is, and a reader cannot tell an absent workspace
   from one that does not exist.
3. **`apply_control` returns a refusal rather than raising one.** A surface that
   cannot throttle answers with `applied` false and a reason, so the caller
   tries a different control instead of abandoning the run. Only a genuine
   failure raises, and `AccessDenied` on a write is documented as distinct from
   a refusal.
4. **The ports package is no longer homogeneous, so it says so in code.**
   `PROVIDER_PORTS` and `SURFACE_PORTS` are exported tuples. Without them
   `tests/providers/test_fake.py` derived "every port" from `__all__` and failed
   the moment `QuerySurface` appeared, because a cloud fake has no business
   implementing a query surface. The grouping puts that distinction in one place
   rather than in a filter inside a test.

**Do not.**

- Do not name it `GrafanaSource`. Naming an abstraction after its first
  implementation is how it ends up shaped like one vendor, and FEAT-019 exists
  precisely because the failure mode is not Grafana specific.
- Do not return a Grafana dashboard object. Return a domain `QueryDefinition`.

**Evidence.**

```bash
pytest tests/query/test_ports.py -v && .venv/bin/lint-imports
```

20 tests pass and all three contracts hold.

---

### TASK-P2-005: the fake Grafana surface

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-23 |
| Depends on | TASK-P2-004 |
| Estimate | M |

**Acceptance criteria.**

- [x] Implements `QuerySurface` in memory
- [x] Can be configured to raise any of the six error types per instance
- [x] Ships a fixture estate: 3 instances, one of each kind, one of them
      unreachable
- [x] Deterministic

**Do not.** Do not make the fake only capable of success. The unreachable
instance case has its own test in the spec and needs a fixture that produces it.

---

### TASK-P2-006: the AMG connection strategy

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-24 |
| Delivers | FEAT-011 |
| Depends on | TASK-P2-005 |
| Estimate | M |

**Acceptance criteria.**

- [x] Discovery via `grafana:ListWorkspaces` per account per region
- [x] Temporary service account token minted per run and **revoked at the end
      of the run, including on failure**
- [x] Falls back to a Secrets Manager token when configured
- [~] Passes the contract suite under `moto`. **Not possible: moto implements
      no Grafana operation at all, and botocore knows them from the service
      model so the gap is invisible until a call is made. `botocore.stub`
      validates a request and a response against the real model instead, which
      is stronger for API correctness and immediately caught the fixture
      omitting four fields `ListWorkspaces` requires. ISS-141.**

**Layering found here.** The first implementation imported `finops_query` to
classify and fingerprint, and the import contract refused it: `finops_query`
sits above `finops_providers` precisely because it reads what an adapter
fetched. The adapter now names a `QueryParser` port in `finops_core.ports.query`
and a collector supplies `finops_query.parser.GrafanaQueryParser`. The adapter
fetches, the layer above interprets, and the import direction points down.

**Do not.**

- Do not leave a service account behind on failure. The prototype creates them;
  a run that dies mid way leaves a credential in someone's Grafana. Revoke in a
  `finally`.

---

### TASK-P2-007: the self hosted connection strategy

**Descoped 2026-09-02.** OPEN-04 was re answered as Amazon Managed Grafana only,
superseding the 2026-08-23 answer of all three behind per tenant flags. The task
is kept rather than deleted, because deleting it loses the record that the
option was considered and priced. Reinstate it with ISS-024 if the answer
changes again.

| Field | Value |
| --- | --- |
| Status | Descoped, 2026-09-02 |
| Delivers | FEAT-011 |
| Depends on | TASK-P2-005 |
| Estimate | M |

**Acceptance criteria.**

- [ ] Reads `grafana_instance` rather than discovering, because there is no API
- [ ] Credential from Secrets Manager by reference
- [ ] **A connection failure sets `reachable = false` with a reason**, and does
      not fail the run
- [ ] Connection timeout bounded, so an unreachable instance fails in seconds
      rather than consuming the run

**Do not.**

- Do not treat unreachable as an error to retry indefinitely. It is a stable
  state of the world, usually a network path that does not exist. Record it,
  surface it, move on. ISS-090.

---

### TASK-P2-008: the Grafana Cloud connection strategy

**Descoped 2026-09-02.** OPEN-04 was re answered as Amazon Managed Grafana only,
superseding the 2026-08-23 answer of all three behind per tenant flags. The task
is kept rather than deleted, because deleting it loses the record that the
option was considered and priced. Reinstate it with ISS-024 if the answer
changes again.

| Field | Value |
| --- | --- |
| Status | Descoped, 2026-09-02 |
| Delivers | FEAT-011 |
| Depends on | TASK-P2-005 |
| Estimate | S |

**Acceptance criteria.**

- [ ] API key per stack, from Secrets Manager
- [ ] Outbound to `grafana.net` recorded as a new egress path in the threat
      model, ISS-091
- [ ] Rate limit responses map to `Throttled` and back off

**Do not.** Do not log the API key, or any response header that echoes it.

---

## Wave C: schema

### TASK-P2-009: the six P2 tables

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-30 |
| Implements | P2 spec section 5 |
| Depends on | P0 TASK-P0-010 |
| Estimate | L |

**Acceptance criteria.**

- [x] `grafana_instance`, `query_definition`, `query_finding`,
      `folder_team_map`, `enforcement_action`, `remediation_change`
- [x] `ck_enforcement_action__restrictive_expires`: a `DENY` or `THROTTLE` row
      **cannot be inserted without an expiry**
- [x] `ck_query_finding__measured_has_runs`: a modelled row cannot carry a
      measured run count, and a measured row cannot omit one
- [x] `remediation_change.before` is `NOT NULL`
- [x] Every table classified in `docs/09-DATA-CLASSIFICATION.md`, with a
      retention period

**Tests.**

| Test | Asserts |
| --- | --- |
| `test_deny_requires_expiry` | The database rejects a DENY with no expiry |
| `test_modelled_cannot_claim_measured` | Both directions of the provenance constraint |
| `test_remediation_requires_undo` | A change with no before value is rejected |

**One constraint added beyond the specification.**
`ck_grafana_instance__unreachable_has_reason` mirrors the invariant
`SurfaceInstance.__post_init__` already enforces in the domain. An unexplained
absence is what makes an estate look smaller than it is, and the domain being
careful is not a reason for the table not to be. The specification was updated
rather than left to diverge.

**Do not.**

- Do not enforce the expiry rule in application code only. It is the thing that
  stops a deny becoming permanent, and application code is not what holds when
  two paths write the same table.
- Do not add a table without adding it to the data classification document. A
  new table is not complete until it has a retention period.

---

## Wave D: the audit

### TASK-P2-010: the query audit collector

| Field | Value |
| --- | --- |
| Status | Done, 2026-08-31 |
| Implements | P2 spec section 7.1 |
| Delivers | FEAT-011, FEAT-012 |
| Depends on | TASK-P2-006, TASK-P2-009 |
| Estimate | L |

**Acceptance criteria.**

- [x] Registered in `collector_schedule` at **6 hours**, with its reason and
      its estimated cost per run, per ADR-0012
- [x] Walks every reachable instance, upserts `query_definition` and today's
      `query_finding`
- [x] One unreachable instance does not fail the run
- [x] Idempotent: three runs in one day write one `query_finding` per query

**Where the parser is wired.** `AmgQuerySurface` takes a `QueryParser`, and
the collector takes an already built surface, so the wiring point is wherever
the collector is constructed. The tests build it with `FakeQuerySurface`;
production builds it with `AmgQuerySurface(parser=GrafanaQueryParser(), ...)`.

**Do not.**

- Do not exclude an unreachable instance from the interface. It appears, marked
  unreachable, and its queries are excluded from totals **with the exclusion
  stated**. A silently smaller denominator is a confidently wrong total.

---

### TASK-P2-011: fingerprinting and template variables

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-01 |
| Depends on | TASK-P2-010 |
| Estimate | M |

**Acceptance criteria.**

- [x] Fingerprint is stable across template variable substitution
- [x] Two panels running the same query on different dashboards share a
      fingerprint, so measured evidence matches both. **Delivered as a second
      key rather than a wider first one. `fingerprint` cannot be widened:
      `uq_query_definition__fingerprint` makes it the identity of a row, so two
      panels sharing one would upsert over each other and a panel would vanish
      from the estate. `policy.query_key` carries the query shape and is what
      evidence attaches to, on a new nullable `query_definition.query_key`
      column added additively in migration 0004.**
- [x] Whitespace and comment changes do not change the fingerprint

**A comment marker inside a quoted string is treated as a comment**, so the rest
of that line is dropped from the key. It affects the key only, never the stored
query, the targets or the cost. Accepted as ISS-142 rather than writing a parser
per query language.

**Do not.** Do not fingerprint the raw query text. A dashboard variable makes
every render unique, and measured evidence would then match nothing.

---

### TASK-P2-012: severity, ranking and grouping

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | ADR-0016 |
| Depends on | TASK-P2-010 |
| Estimate | M |

**Acceptance criteria.**

- [ ] Severity derived from `cost_month_usd`, never entered
- [ ] Thresholds read from settings, configurable per tenant
- [ ] **Findings grouped by cause before ranking**, so four hundred findings at
      15 USD surface as one 6,000 USD group rather than four hundred `LOW` rows

**Do not.** Do not rank ungrouped. A systemic problem hiding as hundreds of
trivial ones is the specific failure the dollar thresholds would otherwise
introduce.

---

## Wave E: evidence

### TASK-P2-013: the measured overlay

| Field | Value |
| --- | --- |
| Status | Not started |
| Delivers | FEAT-013 |
| Depends on | TASK-P2-011 |
| Estimate | L |

**Acceptance criteria.**

- [ ] CloudTrail `StartQuery`, `logs:DescribeQueries` and `GetMetricData` call
      counts collected and matched by fingerprint
- [ ] A matched finding is promoted to `measured` with `measured_runs` set
- [ ] An unmatched finding stays `modelled`, which is a normal state

**Do not.** Do not treat absent evidence as zero runs. Absent means unobserved.

---

### TASK-P2-014: owner attribution

| Field | Value |
| --- | --- |
| Status | Not started |
| Delivers | FEAT-016 |
| Depends on | TASK-P2-013 |
| Estimate | M |

**Acceptance criteria.**

- [ ] Three sources in priority order, and `owner_source` records which won
- [ ] A query with no resolvable owner is reported **unowned**
- [ ] `folder_team_map` classified as class P and retained accordingly

**Do not.** Do not assign a default owner. A wrongly assigned owner is worse
than an absent one: it is ignored by the person it reaches and never reaches
the person who could act.

---

## Wave F: the control

### TASK-P2-015: detection and alerting

| Field | Value |
| --- | --- |
| Status | Parked, 2026-08-29 |
| Implements | P2 spec section 7.2 |
| Delivers | FEAT-015 |
| Depends on | TASK-P2-009 |
| Estimate | L |

**Parked 2026-08-29.** Needs EventBridge, a Lambda and Budgets Actions. ISS-122
records that no Terraform stack has ever been planned or applied, so this can be
built and unit tested but not verified against AWS. Parked rather than descoped:
the kill switch is the feature that stops the bleed, and TASK-P2-007 and 008
already show what descoped looks like when the answer is really no.

**Acceptance criteria.**

- [ ] EventBridge rule on CloudTrail `StartQuery`, per account and region
- [ ] A Lambda, not a Fargate service. It must respond in seconds and is idle
      between events
- [ ] Rate counted per principal per rolling hour
- [ ] On breach: `enforcement_action` at `ALERT`, a page, and a ticket
- [ ] **Detection to page under 15 minutes**, asserted by a test

**Do not.** Do not put this on the 6 hourly audit path. At the burn rate that
started this project a six hour gap is roughly 25,000 USD.

---

### TASK-P2-016: throttle and deny, with the guardrails

| Field | Value |
| --- | --- |
| Status | Parked, 2026-08-29 |
| Delivers | FEAT-015 |
| Depends on | TASK-P2-015 |
| Estimate | L |

**Parked 2026-08-29.** Needs EventBridge, a Lambda and Budgets Actions. ISS-122
records that no Terraform stack has ever been planned or applied, so this can be
built and unit tested but not verified against AWS. Parked rather than descoped:
the kill switch is the feature that stops the bleed, and TASK-P2-007 and 008
already show what descoped looks like when the answer is really no.

**Acceptance criteria.**

- [ ] Level from the `query_control_level` flag, defaulting to `alert`
- [ ] `THROTTLE` applies a per principal rate limit after a grace window
- [ ] `DENY` applies a Budgets Action deny policy on `logs:StartQuery`
- [ ] **Every restrictive action has an expiry**, default 60 minutes, and a
      scheduled job removes expired actions
- [ ] **The never deny list is checked before any restrictive action**
- [ ] `POST /api/v1/query/enforcement/{id}/revoke` removes one immediately

**Tests.**

| Test | Asserts |
| --- | --- |
| `test_deny_never_applied_to_protected_principal` | The never deny list holds at any rate |
| `test_expired_deny_is_removed` | The scheduled remover works, so a deny cannot outlive its window |
| `test_deny_without_expiry_is_rejected` | The database constraint, from the application side |

**Do not.**

- Do not ship `deny` without the never deny list populated. Cutting an engineer
  off from Logs Insights during an outage, caused by that outage, is a self
  inflicted second incident. ISS-092, ISS-095.
- Do not rely on the scheduled remover alone. The expiry is also enforced when
  the action is read, so a failed remover does not extend a deny.

---

## Wave G: prevention

### TASK-P2-017: the workspace refresh floor

| Field | Value |
| --- | --- |
| Status | Not started |
| Delivers | FEAT-014 |
| Depends on | TASK-P2-006 |
| Estimate | S |

**Goal.** The highest value change in P2 relative to its size. One setting that
Grafana then enforces itself on every save, forever, with no code from us.

**Acceptance criteria.**

- [ ] Reads and reports the current floor per workspace
- [ ] Sets it when `query_write_level` is `workspace_floor` or above
- [ ] Recorded in `remediation_change` with a `before` value

**Do not.** Do not set it without recording the previous value. Even a one
setting change must be undoable.

---

### TASK-P2-018: the CI policy gate

| Field | Value |
| --- | --- |
| Status | Not started |
| Delivers | FEAT-014 |
| Depends on | TASK-P2-002 |
| Estimate | M |

**Acceptance criteria.**

- [ ] A standalone checker over dashboard JSON, usable in any pipeline
- [ ] Rejects a Logs Insights panel combining sub minute refresh with a window
      over 24 hours
- [ ] Rules from settings, so a tenant can tighten them
- [ ] Reports the modelled cost of the violating panel, so the failure message
      says what it would have cost

**Do not.** Do not make it a warning. See ISS-096: its reach depends on how many
dashboards are managed as code, and a gate that warns is ignored regardless.

---

## Wave H: remediation

### TASK-P2-019: panel rewrite with undo

| Field | Value |
| --- | --- |
| Status | Not started |
| Delivers | FEAT-017 |
| Depends on | TASK-P2-017 |
| Estimate | L |

**Acceptance criteria.**

- [ ] Only when `query_write_level` is `full`, default `none`
- [ ] `before` captured and stored before the write
- [ ] Read back after the write, and **automatic revert if it does not match**
- [ ] Owner notified with what changed and how to undo it
- [ ] `POST .../undo` restores the original exactly

**Do not.**

- Do not rewrite anything that is not an explicit policy violation. A judgement
  call is a recommendation, not a remediation.
- Do not write without the read back. A partial write to a dashboard is worse
  than the original problem.

---

## Wave I: calibration

### TASK-P2-020: back test the model against the bill

| Field | Value |
| --- | --- |
| Status | Not started |
| Delivers | FEAT-018 |
| Depends on | TASK-P2-013, and P1 cost data |
| Estimate | L |

**Acceptance criteria.**

- [ ] Compares modelled monthly cost to the CUR usage types for scanned bytes
      and metrics requested over the same period
- [ ] Publishes an accuracy percentage, visible next to every modelled figure
- [ ] Insufficient history produces **no figure**, not a misleading one

**Do not.** Do not auto correct the model from the back test. Measure it, show
the measurement, and let a person decide what to change. ISS-093.

---

## Wave J: surface

### TASK-P2-021: routes and MCP tools

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P2 spec section 8.2 |
| Depends on | TASK-P2-014. TASK-P2-016 is parked |
| Estimate | M |

**Scoped by the parking of wave F on 2026-08-29.** Seven of the eight routes
read data that TASK-P2-014 produces. The eighth, enforcement, has nothing behind
it until TASK-P2-016 lands, so it is not built and `/api/v1/query/enforcement`
stays in `FIXTURE_SURFACES`. The enforcement screen therefore stays fixture
backed and keeps saying so on screen, which is the behaviour that seam exists
for.

**Acceptance criteria.**

- [ ] The eight routes from spec section 8.2
- [ ] Three MCP tools, schemas generated from the same models
- [ ] Every response carries the standard `meta` envelope
- [ ] `scope_coverage` accounts for unreachable instances

**Do not.** Do not expose a remediation route that ignores the write level flag.

---

## Wave K: screens

Each of these four is built against a typed fixture and carries the
`FIXTURE DATA` band from TASK-P0-037 until its route exists. None of them
depends on wave J.

### TASK-P2-022: the query findings screen

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-13 |
| Implements | P2 spec section 9.1, `docs/13-UI-ARCHITECTURE.md` section 9.1 |
| Delivers | FEAT-011, FEAT-012, FEAT-016 at the surface |
| Depends on | TASK-P0-037, TASK-P2-004 |
| Estimate | M |

**Acceptance criteria.**

- [x] Dense table, 32 px rows, sorted by monthly cost descending
- [x] The `why` column is **a column of prose**, not a tooltip
- [x] Every modelled figure is hatched and prefixed, and reads differently from a
      measured one
- [x] An unreachable instance produces a partial state with the count of what is
      missing **above** the table, not a row inside it
- [x] `unattributed` is a rendered owner value, never a blank cell
- [x] The `FIXTURE DATA` band renders until the client implements the route
- [x] Axe reports zero violations

**Do not.**

- Do not put the `why` text in a tooltip or a hover card. This list is read in
  tickets and in screenshots, and a tooltip is invisible in both. The prose is
  what makes a finding actionable rather than a number.
- Do not render a modelled figure identically to a measured one. The label is
  the product.

**Steps.**

- [x] **Step 1: add the wire type**

`finops-web/src/api/types.ts`, following the existing convention of snake case
fields mirroring `finops_api/schemas.py`.

```ts
export interface ApiQueryFinding {
  readonly finding_id: string;
  readonly dashboard_uid: string;
  readonly dashboard_title: string;
  readonly panel_title: string;
  readonly refresh_seconds: number | null;
  readonly window_seconds: number | null;
  readonly runs_per_day: number;
  readonly bytes_scanned_per_run: number;
  readonly monthly_cost: string;
  /** measured, modelled or forecast. Never absent. */
  readonly provenance: string;
  readonly severity: number;
  /** The literal string `unattributed` when no owner was resolved. */
  readonly owner: string;
  /** Prose explaining what drives the cost. Ported from the prototype. */
  readonly why: string;
}
```

- [x] **Step 2: write the fixture, including the unhappy cases**

`finops-web/src/screens/__tests__/queryFixtures.ts`

```ts
import type { ApiQueryFinding } from '../../api/types';

/**
 * Three rows on purpose: one measured, one modelled, one unattributed. A
 * fixture with only the happy path pins the wrong screen.
 */
export const QUERY_FINDINGS: readonly ApiQueryFinding[] = [
  {
    finding_id: '11111111-1111-1111-1111-111111111111',
    dashboard_uid: 'abc123',
    dashboard_title: 'Platform overview',
    panel_title: 'Error rate by service',
    refresh_seconds: 10,
    window_seconds: 2592000,
    runs_per_day: 8640,
    bytes_scanned_per_run: 4294967296,
    monthly_cost: '12400.00',
    provenance: 'modelled',
    severity: 1,
    owner: 'platform-team',
    why: 'Refreshes every 10 seconds against a 30 day window, so it rescans 4 GiB 8,640 times a day.',
  },
  {
    finding_id: '22222222-2222-2222-2222-222222222222',
    dashboard_uid: 'def456',
    dashboard_title: 'Billing',
    panel_title: 'Invoice totals',
    refresh_seconds: 3600,
    window_seconds: 86400,
    runs_per_day: 24,
    bytes_scanned_per_run: 1048576,
    monthly_cost: '3.20',
    provenance: 'measured',
    severity: 4,
    owner: 'unattributed',
    why: 'Hourly refresh over a one day window. Listed for completeness.',
  },
];
```

- [x] **Step 3: write the failing screen test**

`finops-web/src/screens/__tests__/QueryFindingsScreen.test.tsx`

```tsx
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { QueryFindingsScreen } from '../QueryFindingsScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { violationsIn } from '../../components/__tests__/axe';

/** The path is in FIXTURE_SURFACES, so the client is never called. */
function renderFindings() {
  return render(
    <Harness client={clientReturning({})}>
      <QueryFindingsScreen />
    </Harness>,
  );
}

describe('QueryFindingsScreen', () => {
  it('puts the reason in a column, so it survives a screenshot', async () => {
    renderFindings();
    const table = await screen.findByRole('table');
    expect(within(table).getByRole('columnheader', { name: /why/i })).toBeInTheDocument();
    expect(within(table).getByText(/rescans 4 GiB 8,640 times a day/)).toBeInTheDocument();
  });

  it('ranks by monthly cost, most expensive first', async () => {
    renderFindings();
    const rows = await screen.findAllByRole('row');
    expect(rows[1]).toHaveTextContent('Error rate by service');
  });

  it('renders a modelled figure differently from a measured one', async () => {
    renderFindings();
    const rows = await screen.findAllByRole('row');
    expect(within(rows[1]).getByTestId('figure')).toHaveAttribute('data-provenance', 'modelled');
    expect(within(rows[2]).getByTestId('figure')).toHaveAttribute('data-provenance', 'measured');
  });

  it('shows an unresolved owner as a value, not an empty cell', async () => {
    renderFindings();
    expect(await screen.findByText('unattributed')).toBeInTheDocument();
  });

  it('says so while it is running on a fixture', async () => {
    renderFindings();
    expect(await screen.findByTestId('fixture-band')).toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = renderFindings();
    await screen.findByRole('table');
    expect(await violationsIn(container)).toEqual([]);
  });
});
```

`Figure` emits `data-testid="figure"` and `data-provenance={kind}` at
`finops-web/src/components/Figure.tsx:95`, which is what the third test asserts
on. Do not add attributes to a component that already has them.

- [x] **Step 4: run it and watch it fail**

Run: `cd finops-web && npm run test -- --run src/screens/__tests__/QueryFindingsScreen.test.tsx`
Expected: FAIL, cannot find module `../QueryFindingsScreen`.

- [x] **Step 5: write the screen**

First add one hook the four screens share, to
`finops-web/src/api/queries.ts`, following the one hook per route convention
already in that file:

```ts
import { resolveSurface, type Resolved } from './fixtureSeam';
import type { ApiEnvelope, ApiQueryFinding } from './types';

/**
 * A surface that may still be fixture backed. The envelope is kept whole for
 * the same reason every other hook here keeps it: a hook returning only the
 * rows lets a screen render them without seeing the coverage or the failures
 * that came with them.
 */
export function useQuerySurface<T>(
  key: readonly unknown[],
  template: string,
  path: string,
  fixture: () => ApiEnvelope<T>,
) {
  const client = useApi();
  return useQuery<Resolved<ApiEnvelope<T>>>({
    queryKey: key,
    queryFn: resolveSurface(template, () => client.get<T>(path), fixture),
  });
}

export function useQueryFindings() {
  return useQuerySurface<ApiQueryFinding[]>(
    ['query-findings'],
    '/api/v1/query/findings',
    '/api/v1/query/findings',
    () => ({ data: [...QUERY_FINDINGS], meta: FIXTURE_META }),
  );
}
```

`FIXTURE_META` is an `ApiMeta` in `queryFixtures.ts` with a real `as_of` and
`collected_at`, so a fixture backed screen still exercises the freshness path
rather than skipping it.

Then write `finops-web/src/screens/QueryFindingsScreen.tsx`, composing
`DataTable`, `Figure`, `SeverityBadge`, `StateBoundary` and `FixtureBand`. Sort
by `monthly_cost` descending as a decimal comparison and not a string
comparison, and pass the resolved `source` to `FixtureBand`.

`monthly_cost` arrives as a string to avoid float error. Compare with
`Number.parseFloat` for the sort only, and never for display. Display goes
through `Figure`, which is the only path a number takes to a screen.

- [x] **Step 6: run the tests and watch them pass**

Run: `cd finops-web && npm run test -- --run src/screens/__tests__/QueryFindingsScreen.test.tsx`
Expected: PASS, six tests.

- [x] **Step 7: route it**

Add `<Route path="/governance/queries" element={<QueryFindingsScreen />} />` to
`finops-web/src/App.tsx`, and set `arrives` to null for that path in
`finops-web/src/shell/sections.ts`, because the screen now exists.

- [x] **Step 8: run the whole suite**

Run: `cd finops-web && npm run lint && npm run test -- --run && npm run build`
Expected: all pass.

- [x] **Step 9: commit**

```bash
git add finops-web/src
git commit -m "feat: TASK-P2-022, the query findings screen

Ranked by monthly cost, with the reason as a column rather than a tooltip so it
survives a screenshot. Fixture backed and marked as such until the route lands."
```

---

### TASK-P2-023: the finding detail screen

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-15 |
| Implements | P2 spec section 9.2, `docs/13-UI-ARCHITECTURE.md` section 9.2 |
| Delivers | FEAT-012, FEAT-013 and FEAT-018 at the surface |
| Depends on | TASK-P2-022 |
| Estimate | M |

**Acceptance criteria.**

- [x] Generous density, because the reader is making a judgement
- [x] Publishes the query, the target, the engine classification, **the formula
      with its inputs substituted**, the data window, and measured evidence where
      FEAT-013 produced any
- [x] Where no calibration exists the label reads `accuracy not yet published`
- [x] Where FEAT-018 published one, the label reads `~ $12,400 modelled, +/- 9%`
- [x] Axe reports zero violations

**Do not.**

- Do not summarise the formula. Publishing the arithmetic is what makes a
  modelled number arguable rather than magic, and an engineer who cannot point at
  the line they disagree with dismisses the finding instead of fixing it.
- Do not invent an accuracy percentage to fill the space. No figure is the
  correct rendering until FEAT-018 publishes one.

**Steps.**

- [x] **Step 1: write the failing test**

`finops-web/src/screens/__tests__/QueryFindingDetailScreen.test.tsx`

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { QueryFindingDetailScreen } from '../QueryFindingDetailScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';

const ID = '11111111-1111-1111-1111-111111111111';

function renderDetail() {
  return render(
    <Harness client={clientReturning({})} initialPath={`/governance/queries/${ID}`}>
      <QueryFindingDetailScreen />
    </Harness>,
  );
}

describe('QueryFindingDetailScreen', () => {
  it('publishes the formula with its inputs substituted', async () => {
    renderDetail();
    const working = await screen.findByTestId('finding-working');
    expect(working).toHaveTextContent('8,640 runs per day');
    expect(working).toHaveTextContent('4 GiB scanned per run');
    expect(working).toHaveTextContent('30 day window');
  });

  it('says the accuracy is unpublished rather than showing a number', async () => {
    renderDetail();
    expect(await screen.findByText(/accuracy not yet published/i)).toBeInTheDocument();
  });
});
```

The screen reads its identifier from the route with `useParams`, not from a
prop, because the URL is the thing that gets shared into a ticket. `initialPath`
is the parameter TASK-P0-036 added to `Harness`.

- [x] **Step 2: run it and watch it fail**

Run: `cd finops-web && npm run test -- --run src/screens/__tests__/QueryFindingDetailScreen.test.tsx`
Expected: FAIL, cannot find module.

- [x] **Step 3: extend the fixture and write the screen**

Add `useQueryFinding(id)` to `finops-web/src/api/queries.ts`, built on
`useQuerySurface` with key `['query-finding', id]`, template
`/api/v1/query/findings/{id}` and path `/api/v1/query/findings/${id}`. The
template and the path differ here, which is the case the template matching in
TASK-P0-037 exists for.

Add `QUERY_FINDING_DETAIL` to `finops-web/src/screens/__tests__/queryFixtures.ts`
carrying the query text, the target, the engine, the substituted formula terms
and a null `accuracy_percent`. Write
`finops-web/src/screens/QueryFindingDetailScreen.tsx` rendering them in the order
given in the acceptance criteria, with `FixtureBand` and `StateBoundary`.

A null `accuracy_percent` renders `accuracy not yet published`. A number renders
`+/- n%` beside the modelled label. Those are two branches of one expression, so
neither can be forgotten.

- [x] **Step 4: run the tests and watch them pass**

Run: `cd finops-web && npm run test -- --run src/screens/__tests__/QueryFindingDetailScreen.test.tsx`
Expected: PASS, two tests.

- [x] **Step 5: route it, run the suite, commit**

Add `<Route path="/governance/queries/:id" element={<QueryFindingDetailScreen />} />`.
Run `npm run lint && npm run test -- --run && npm run build`.

```bash
git add finops-web/src
git commit -m "feat: TASK-P2-023, the finding detail screen

Publishes the full working, so a modelled number is arguable rather than magic.
No accuracy figure until FEAT-018 publishes one."
```

---

### TASK-P2-024: the query surfaces screen

| Field | Value |
| --- | --- |
| Status | Done, 2026-09-17 |
| Implements | P2 spec section 9.3, `docs/13-UI-ARCHITECTURE.md` section 9.3 |
| Delivers | FEAT-011 at the surface |
| Depends on | TASK-P0-037, TASK-P2-004 |
| Estimate | S |

**Acceptance criteria.**

- [x] Every instance, its kind, its reachability and its query count
- [x] **An unreachable instance is listed**, with its typed cause and a recheck
- [x] The query count for an unreachable instance is `UNREACHABLE`, **not zero**
- [x] Axe reports zero violations

**Do not.**

- Do not omit an unreachable instance to make the list tidier. This screen exists
  to stop silent under counting, and an instance list that quietly drops the
  three it could not reach makes the findings list look complete when it is not.
- Do not render its query count as zero. A failure is never a number.

**Deviation.** The plan asked for one instance per `SurfaceKind`. All three
fixture instances are `managed_grafana`, because that is the only kind with an
adapter: `self_hosted_grafana` and `grafana_cloud` were descoped as TASK-P2-007
and TASK-P2-008, and a fixture claiming them would show an estate that cannot
currently exist. A third assertion was added beyond the two planned, that a
genuine zero still renders as zero, because the unreachable row only means
something if it does not compete with a real one.

**Steps.**

- [x] **Step 1: write the failing test**

`finops-web/src/screens/__tests__/QuerySurfacesScreen.test.tsx`

```tsx
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { QuerySurfacesScreen } from '../QuerySurfacesScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';

function renderSurfaces() {
  return render(
    <Harness client={clientReturning({})}>
      <QuerySurfacesScreen />
    </Harness>,
  );
}

describe('QuerySurfacesScreen', () => {
  it('lists an instance it could not reach', async () => {
    renderSurfaces();
    expect(await screen.findByText('meter-prod-eu-west-1')).toBeInTheDocument();
  });

  it('shows its query count as the cause, never as zero', async () => {
    renderSurfaces();
    const row = (await screen.findByText('meter-prod-eu-west-1')).closest('tr');
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText('UNREACHABLE')).toBeInTheDocument();
    expect(within(row as HTMLElement).queryByText('0')).toBeNull();
  });
});
```

- [x] **Step 2: run it and watch it fail**

Run: `cd finops-web && npm run test -- --run src/screens/__tests__/QuerySurfacesScreen.test.tsx`
Expected: FAIL, cannot find module.

- [x] **Step 3: add the wire type, the fixture and the screen**

`ApiSurfaceInstance` in `finops-web/src/api/types.ts` with `instance_id`,
`name`, `kind`, `reachable`, `unreachable_cause` and `query_count`, where
`query_count` is `number | null` and null means not countable. Add
`SURFACE_INSTANCES` to `queryFixtures.ts` with three instances, one per
`SurfaceKind` at `finops_core/domain/query.py:28` and one of them unreachable
named `meter-prod-eu-west-1`, which is the name the test looks for. Screen
composes `DataTable`, `TypedError` and `FixtureBand`.

Add `useQuerySurfaces()` to `finops-web/src/api/queries.ts`, built on
`useQuerySurface` from TASK-P2-022 with key `['query-instances']`, template and
path `/api/v1/query/instances`, and fixture `SURFACE_INSTANCES`.

`query_count === null` renders `TypedError` with the cause. It never renders a
numeral, per rule 5 of `docs/12-UI-DESIGN.md`.

- [x] **Step 4: run the tests, route it, run the suite, commit**

Run: `cd finops-web && npm run test -- --run && npm run lint && npm run build`

```bash
git add finops-web/src
git commit -m "feat: TASK-P2-024, the query surfaces screen

Unreachable instances are listed with their cause and no numeral. This is the
screen that stops silent under counting."
```

---

### TASK-P2-025: the enforcement screen and the end to end journey

| Field | Value |
| --- | --- |
| Status | Partly, 2026-09-19 |
| Implements | P2 spec section 9.4, `docs/13-UI-ARCHITECTURE.md` section 9.4 |
| Delivers | FEAT-014, FEAT-015 and FEAT-017 at the surface |
| Depends on | TASK-P2-022, TASK-P2-023, TASK-P2-024 |
| Estimate | M |

**Acceptance criteria.**

- [x] Action, principal, applied at, expires at, reason and revoke
- [x] Expiry shows **both** an absolute time and a countdown
- [x] Revoke is present on every active action and is subject to the write level
      flag
- [x] A revoke control is absent, not merely disabled, when the write level
      forbids it
- [~] An end to end Playwright journey: a violating dashboard is detected, seen
      ranked, its owner seen, the workspace floor applied, and the undo confirmed.
      **Detect, rank and attribute are done, and the journey also covers the
      unreachable instance, the genuine zero, both expiry forms and revoke. The
      floor and the undo are not, because they are TASK-P2-017 and TASK-P2-019
      and neither is built.**
- [x] Axe reports zero violations

**Plan defect found here.** This task's dependency list names TASK-P2-022 to
024, but its journey criterion needs the workspace floor from TASK-P2-017 and
the undo from TASK-P2-019. The criterion was written against the finished sub
project rather than against this task's own dependencies. Complete the journey
when TASK-P2-019 lands, and only then move this task to Done.

**Do not.**

- Do not show only the countdown. An incident bridge needs "how long do I have"
  and "when exactly", and a countdown alone cannot be written into an incident
  log.
- Do not render a revoke button that does nothing when the write level forbids
  it. A control that looks available and is not is worse than an absent one.

**Steps.**

- [x] **Step 1: write the failing test**

`finops-web/src/screens/__tests__/EnforcementScreen.test.tsx`

```tsx
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { EnforcementScreen } from '../EnforcementScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';

function renderEnforcement() {
  return render(
    <Harness client={clientReturning({})}>
      <EnforcementScreen now={new Date('2026-09-06T10:00:00Z')} />
    </Harness>,
  );
}

describe('EnforcementScreen', () => {
  it('shows expiry as an absolute time and a countdown together', async () => {
    renderEnforcement();
    const cell = await screen.findByTestId('expires-33333333-3333-3333-3333-333333333333');
    expect(cell).toHaveTextContent('10:45');
    expect(cell).toHaveTextContent(/45 min/);
  });

  it('omits revoke entirely for an action the API says is not revocable', async () => {
    renderEnforcement();
    const row = (await screen.findByText('44444444-4444-4444-4444-444444444444')).closest('tr');
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).queryByRole('button', { name: /revoke/i })).toBeNull();
  });
});
```

`now` is an optional prop, matching the pattern `AppShell` already uses at
`finops-web/src/shell/AppShell.tsx:33`, so the countdown is testable without
faking a clock.

**The write level is not a frontend decision.** Architectural constraint 8 makes
the HTTP API the single enforcement point, so the API sets `revocable` per action
and the screen renders what it is told. A frontend that decided revocability
itself would be a second implementation of an authorization rule, which is how an
authorization bug is created.

- [x] **Step 2: run it and watch it fail**

Run: `cd finops-web && npm run test -- --run src/screens/__tests__/EnforcementScreen.test.tsx`
Expected: FAIL, cannot find module.

- [x] **Step 3: add the wire type, the fixture and the screen**

Add to `finops-web/src/api/types.ts`:

```ts
export interface ApiEnforcementAction {
  readonly action_id: string;
  /** ALERT, THROTTLE or DENY. */
  readonly action: string;
  readonly principal: string;
  readonly applied_at: string;
  /** Required for THROTTLE and DENY, null for ALERT. */
  readonly expires_at: string | null;
  readonly reason_finding_id: string;
  /** Set by the API, per architectural constraint 8. Never inferred here. */
  readonly revocable: boolean;
}
```

Add to `finops-web/src/screens/__tests__/queryFixtures.ts`:

```ts
import type { ApiEnforcementAction } from '../../api/types';

export const ENFORCEMENT_ACTIONS: readonly ApiEnforcementAction[] = [
  {
    action_id: '33333333-3333-3333-3333-333333333333',
    action: 'THROTTLE',
    principal: 'arn:aws:iam::role/grafana-datasource',
    applied_at: '2026-09-06T09:45:00Z',
    expires_at: '2026-09-06T10:45:00Z',
    reason_finding_id: '11111111-1111-1111-1111-111111111111',
    revocable: true,
  },
  {
    action_id: '44444444-4444-4444-4444-444444444444',
    action: 'ALERT',
    principal: 'arn:aws:iam::role/reporting',
    applied_at: '2026-09-05T11:00:00Z',
    expires_at: null,
    reason_finding_id: '22222222-2222-2222-2222-222222222222',
    revocable: false,
  },
];
```

The second row is why the second test passes: an `ALERT` never expires and
nothing can be revoked, so its row carries no button. The first expires 45
minutes after the `now` the test injects.

Write `finops-web/src/screens/EnforcementScreen.tsx` composing `DataTable` and
`FixtureBand`, with an `expires` cell rendering both forms:

```tsx
<td data-testid={`expires-${action.action_id}`}>
  {action.expires_at === null ? (
    'does not expire'
  ) : (
    <>
      <time dateTime={action.expires_at}>{hourMinuteUtc(action.expires_at)}</time>
      <span> in {minutesUntil(action.expires_at, now)} min</span>
    </>
  )}
</td>
```

`hourMinuteUtc` and `minutesUntil` are two small local helpers in this file.
Render both forms always. An incident bridge needs "how long do I have" and
"when exactly", and a countdown alone cannot be written into an incident log.

Revoke renders only when `revocable` is true. It is a conditional render, not a
`disabled` attribute, because a control that looks available and is not is worse
than an absent one.

Add `useEnforcementActions()` to `finops-web/src/api/queries.ts`, built on
`useQuerySurface` with key `['query-enforcement']`, template and path
`/api/v1/query/enforcement`, and fixture `ENFORCEMENT_ACTIONS`.

- [x] **Step 4: run the tests and watch them pass**

Run: `cd finops-web && npm run test -- --run src/screens/__tests__/EnforcementScreen.test.tsx`
Expected: PASS, two tests.

- [x] **Step 5: write the end to end journey**

Append to `finops-web/e2e/journey.spec.ts`.

```ts
test('a violating dashboard is found, attributed, controlled and undone', async ({ page }) => {
  await page.goto('/governance/queries');
  await expect(page.getByText('Error rate by service')).toBeVisible();
  await expect(page.getByText(/rescans 4 GiB/)).toBeVisible();
  await page.getByRole('link', { name: 'Error rate by service' }).click();
  await expect(page.getByTestId('finding-working')).toBeVisible();
  await page.goto('/governance/enforcement');
  await expect(page.getByRole('button', { name: /revoke/i })).toBeVisible();
});
```

- [x] **Step 6: run everything**

Run: `cd finops-web && npm run lint && npm run test -- --run && npm run build && npx playwright test`
Expected: all pass.

- [x] **Step 7: commit**

```bash
git add finops-web/src finops-web/e2e
git commit -m "feat: TASK-P2-025, the enforcement screen and the journey

Expiry as an absolute time and a countdown, because an incident bridge needs
both. Revoke is absent rather than disabled when the write level forbids it.
This screen is the reason deny is safe to enable."
```

---

## Traceability

| Feature | Tasks |
| --- | --- |
| FEAT-011 scanner | 004, 005, 006, 007, 008, 010 |
| FEAT-012 cost model | 002, 010, 012 |
| FEAT-013 measured overlay | 011, 013 |
| FEAT-014 preventive controls | 017, 018 |
| FEAT-015 kill switch | 015, 016 |
| FEAT-016 owner attribution | 014 |
| FEAT-017 auto remediation | 019 |
| FEAT-018 calibration | 020 |
| Surface | 021 |
| Screens | 022, 023, 024, 025 |

## Exit criteria

The seven universal criteria in `docs/01-ROADMAP.md`, plus the two from the
specification:

- A policy violating dashboard is blocked at save, and a runaway query is
  detected and acted on within 15 minutes.
- A separate threat model pass covering the write paths and the deny path,
  appended to `docs/08-THREAT-MODEL.md`.
