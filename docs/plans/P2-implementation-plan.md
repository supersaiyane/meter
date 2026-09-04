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
| J. Surface | 021 to 022 | Routes, MCP tools and four screens | D to H |

Waves F and G do not depend on D. With two people, one takes the audit path and
the other takes control and prevention, which is also the fastest route to the
thing that actually stops the bleed.

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
| Status | Not started |
| Implements | P2 spec section 4.1 |
| Delivers | FEAT-011 |
| Depends on | TASK-P2-003 |
| Estimate | M |

**Acceptance criteria.**

- [ ] `QuerySurface` in `finops_core/ports/`, with `discover`, `list_queries`
      and `apply_control`
- [ ] No Grafana type appears in any signature
- [ ] The import linter contract is extended to cover `finops_query`
- [ ] Each method documents which of the six error types it may raise

**Do not.**

- Do not name it `GrafanaSource`. Naming an abstraction after its first
  implementation is how it ends up shaped like one vendor, and FEAT-019 exists
  precisely because the failure mode is not Grafana specific.
- Do not return a Grafana dashboard object. Return a domain `QueryDefinition`.

**Evidence.** `pytest tests/query/test_ports.py -v && .venv/bin/lint-imports`

---

### TASK-P2-005: the fake Grafana surface

| Field | Value |
| --- | --- |
| Status | Not started |
| Depends on | TASK-P2-004 |
| Estimate | M |

**Acceptance criteria.**

- [ ] Implements `QuerySurface` in memory
- [ ] Can be configured to raise any of the six error types per instance
- [ ] Ships a fixture estate: 3 instances, one of each kind, one of them
      unreachable
- [ ] Deterministic

**Do not.** Do not make the fake only capable of success. The unreachable
instance case has its own test in the spec and needs a fixture that produces it.

---

### TASK-P2-006: the AMG connection strategy

| Field | Value |
| --- | --- |
| Status | Not started |
| Delivers | FEAT-011 |
| Depends on | TASK-P2-005 |
| Estimate | M |

**Acceptance criteria.**

- [ ] Discovery via `grafana:ListWorkspaces` per account per region
- [ ] Temporary service account token minted per run and **revoked at the end
      of the run, including on failure**
- [ ] Falls back to a Secrets Manager token when configured
- [ ] Passes the contract suite under `moto`

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
| Status | Not started |
| Implements | P2 spec section 5 |
| Depends on | P0 TASK-P0-010 |
| Estimate | L |

**Acceptance criteria.**

- [ ] `grafana_instance`, `query_definition`, `query_finding`,
      `folder_team_map`, `enforcement_action`, `remediation_change`
- [ ] `ck_enforcement_action__restrictive_expires`: a `DENY` or `THROTTLE` row
      **cannot be inserted without an expiry**
- [ ] `ck_query_finding__measured_has_runs`: a modelled row cannot carry a
      measured run count, and a measured row cannot omit one
- [ ] `remediation_change.before` is `NOT NULL`
- [ ] Every table classified in `docs/09-DATA-CLASSIFICATION.md`, with a
      retention period

**Tests.**

| Test | Asserts |
| --- | --- |
| `test_deny_requires_expiry` | The database rejects a DENY with no expiry |
| `test_modelled_cannot_claim_measured` | Both directions of the provenance constraint |
| `test_remediation_requires_undo` | A change with no before value is rejected |

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
| Status | Not started |
| Implements | P2 spec section 7.1 |
| Delivers | FEAT-011, FEAT-012 |
| Depends on | TASK-P2-006, TASK-P2-009 |
| Estimate | L |

**Acceptance criteria.**

- [ ] Registered in `collector_schedule` at **6 hours**, with its reason and
      its estimated cost per run, per ADR-0012
- [ ] Walks every reachable instance, upserts `query_definition` and today's
      `query_finding`
- [ ] One unreachable instance does not fail the run
- [ ] Idempotent: three runs in one day write one `query_finding` per query

**Do not.**

- Do not exclude an unreachable instance from the interface. It appears, marked
  unreachable, and its queries are excluded from totals **with the exclusion
  stated**. A silently smaller denominator is a confidently wrong total.

---

### TASK-P2-011: fingerprinting and template variables

| Field | Value |
| --- | --- |
| Status | Not started |
| Depends on | TASK-P2-010 |
| Estimate | M |

**Acceptance criteria.**

- [ ] Fingerprint is stable across template variable substitution
- [ ] Two panels running the same query on different dashboards share a
      fingerprint, so measured evidence matches both
- [ ] Whitespace and comment changes do not change the fingerprint

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
| Status | Not started |
| Implements | P2 spec section 7.2 |
| Delivers | FEAT-015 |
| Depends on | TASK-P2-009 |
| Estimate | L |

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
| Status | Not started |
| Delivers | FEAT-015 |
| Depends on | TASK-P2-015 |
| Estimate | L |

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
| Depends on | TASK-P2-014, TASK-P2-016 |
| Estimate | M |

**Acceptance criteria.**

- [ ] The eight routes from spec section 8.2
- [ ] Three MCP tools, schemas generated from the same models
- [ ] Every response carries the standard `meta` envelope
- [ ] `scope_coverage` accounts for unreachable instances

**Do not.** Do not expose a remediation route that ignores the write level flag.

---

### TASK-P2-022: four screens

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | P2 spec section 9 |
| Depends on | TASK-P2-021 |
| Estimate | L |

**Acceptance criteria.**

- [ ] Findings, ranked by cost, with the `why` column in prose
- [ ] Finding detail showing the full working: query, target, formula, window,
      and measured evidence where it exists
- [ ] Instances, **including unreachable ones**
- [ ] Enforcement, showing active actions, their expiry, and a revoke button
- [ ] Every modelled figure carries its caveat until FEAT-018 publishes accuracy
- [ ] An end to end journey: detect a violating dashboard, see it ranked, see
      its owner, apply the workspace floor, confirm the undo

**Do not.**

- Do not render a modelled figure identically to a measured one. The label is
  the product.
- Do not hide unreachable instances to make the list tidier. That screen exists
  to stop silent under counting.

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
| Surface | 021, 022 |

## Exit criteria

The seven universal criteria in `docs/01-ROADMAP.md`, plus the two from the
specification:

- A policy violating dashboard is blocked at save, and a runaway query is
  detected and acted on within 15 minutes.
- A separate threat model pass covering the write paths and the deny path,
  appended to `docs/08-THREAT-MODEL.md`.
