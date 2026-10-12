# P12 Deployment readiness: implementation plan

Date: 2026-10-12
Status: Approved by the owner on 2026-10-12 with OPEN-28 and OPEN-29 answered, in build
Spec: `docs/specs/2026-10-12-p12-deployment-readiness-design.md`
Depends on: P0 to P11 delivered against fakes. Proof against a real estate waits on ISS-002
Tasks: 9

Every sub project is delivered against fakes, and a deployed Meter would still collect nothing.
This sub project makes the platform run outside its tests: one composition of every collector,
a dispatcher and a worker that run, the deployed settings in SSM Parameter Store, a pipeline that
applies its own plan, and the owner's steps for the first account.

## How to work this plan

Same contract as P0 through P11. One task, one commit, `make verify` green before a merge.

**Three rules specific to P12.**

1. **No fake in a deployment.** The fakes run only in the local stack, through their own entry
   points, ADR-0022; nothing a deployed process can set switches it onto them.
2. **A collector with no AWS adapter fails typed, never on a fake.** In AWS mode it is registered
   and every run is Misconfigured, naming the missing adapter, ISS-240.
3. **No secret in git or in the Terraform state.** Secret parameters are created with a placeholder
   and their values are set by the owner.

## Wave overview

| Wave | Tasks | Delivers | Can start when |
| --- | --- | --- | --- |
| A. The composition | 001, 002 | Every collector registered, for a deployment and the local stack | This plan approved |
| B. The processes | 003, 004, 005 | The queue, the two entry points, the local stack end to end | A |
| C. The deploy | 006, 007 | Settings in SSM, each deploy its own plan | Any time |
| D. The first account | 008 | The runbook and `make first-contact` | A |
| E. Proof and documents | 009 | Exit criteria measured and the documents | All |

Modelled at the pace of P11: eight tasks of size M and one of size S, about eight working days.

---

### TASK-P12-001: the two compositions

| Field | Value |
| --- | --- |
| Status | Done 2026-10-12 |
| Implements | Spec section 5.1, OPEN-28 |
| Delivers | FEAT-079 |
| Depends on | Nothing |
| Estimate | M |

**Acceptance criteria.**

- [x] `finops_ingest/composition.py` binds every collector the worker runs for a deployment, the
      ones that read only Meter for real and the rest failing typed until TASK-P12-002
- [x] `finops_fakes/composition.py` binds the same collectors from the fakes, on a clock it is
      handed, for the local stack only
- [x] A test fails when a collector the worker runs is missing from either

---

### TASK-P12-002: the AWS binders

| Field | Value |
| --- | --- |
| Status | Done 2026-10-12 |
| Implements | Spec section 5.1 |
| Delivers | FEAT-079 |
| Depends on | TASK-P12-001 |
| Estimate | M |

**Acceptance criteria.**

- [x] In AWS mode each collector is built from the AWS adapters on the unit's session: 17 of them,
      in `finops_ingest/aws_bindings.py`, through `finops_providers/aws/reach.py`
- [x] A collector that cannot be built for AWS fails each run as Misconfigured, naming why: three
      ports with no adapter, ISS-240, and `query_audit`, which no setting can configure, ISS-272;
      a read whose setting is not set names the setting
- [x] A test builds every collector in AWS mode over a stubbed session and finds no fake in it,
      and building makes no AWS client

---

### TASK-P12-003: the queue, published and consumed

| Field | Value |
| --- | --- |
| Status | Done 2026-10-12 |
| Implements | Spec section 5.3 |
| Delivers | FEAT-079 |
| Depends on | Nothing |
| Estimate | M |

**Acceptance criteria.**

- [x] An SQS publisher for the dispatcher and a consumer for the worker, over boto3:
      `finops_ingest/sqs.py`, handed its client, with a versioned message
- [x] A unit survives the round trip unchanged, tested under moto
- [x] A message the worker cannot decode is left for the redrive and logged, never dropped:
      under moto it is received again and then moved to the dead letter queue intact

---

### TASK-P12-004: the dispatcher and the worker as processes

| Field | Value |
| --- | --- |
| Status | Done 2026-10-12 |
| Implements | Spec section 5.2 |
| Delivers | FEAT-079 |
| Depends on | TASK-P12-001, TASK-P12-003 |
| Estimate | M |

**Acceptance criteria.**

- [x] `python -m finops_ingest.dispatcher` publishes each tenant's due units, then exits: windows
      aligned to each collector's cadence, one tenant failing logged and the rest dispatched
- [x] `python -m finops_ingest.worker` long polls, runs each batch, deletes what succeeded, and
      stops between units on SIGTERM; the worker's ECS stop timeout is 120 seconds
- [x] Both refuse to start when their settings are incomplete, naming what is missing, tested by
      running the entry points; the local stack runs the same two processes on the fakes through
      `python -m finops_fakes.dispatcher` and `.worker`. Amended 2026-10-12: TASK-P12-001 removed
      `METER_PROVIDERS`, so the entry point, not a setting, chooses the composition
- [x] Found and fixed on the way: the runtime images did not copy `finops_relay`, ISS-274, and a
      dispatch refused a second tenant's units as duplicates of the first's, ISS-275

---

### TASK-P12-005: the local stack, end to end

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec sections 2 and 5.2 |
| Delivers | FEAT-079 |
| Depends on | TASK-P12-004 |
| Estimate | M |

**Acceptance criteria.**

- [ ] `make up` runs the dispatcher and the worker on fakes against LocalStack's queue
- [ ] A test proves one collector dispatched, queued, claimed, run and recorded in `ingest_run`
- [ ] The runbook for the local stack says how to watch it

---

### TASK-P12-006: deployed settings in SSM Parameter Store

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 5.4, OPEN-29, ISS-250 |
| Delivers | FEAT-080 |
| Depends on | TASK-P12-001 |
| Estimate | M |

**Acceptance criteria.**

- [ ] One parameter per setting under `/meter/<env>/`, the values that are not secret from a
      committed map per environment, the secret ones created with a placeholder and never managed
- [ ] Every task definition reads its settings through `secrets` with `valueFrom`, and the
      execution role reads only its own environment's path
- [ ] A test holds every field of the settings model to a parameter, among them
      `METER_RELAY_FUNCTION_NAME` from the hub's relay and `METER_CONFIG_AGGREGATOR` from the config
      stack's output, which TASK-P12-002 added

---

### TASK-P12-007: each deploy applies its own plan

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 5.5, ISS-260 |
| Delivers | FEAT-080 |
| Depends on | Nothing |
| Estimate | S |

**Acceptance criteria.**

- [ ] One plan file per environment, and each deploy job needs its own environment's plan job
- [ ] A test reads `.gitlab-ci.yml` and fails if two jobs share a plan path or a deploy needs a
      job that publishes no plan

---

### TASK-P12-008: the first account, a runbook and a first contact

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 5.6, ISS-002, ISS-122, ISS-111, ISS-179 |
| Delivers | FEAT-079 |
| Depends on | TASK-P12-002 |
| Estimate | M |

**Acceptance criteria.**

- [ ] `docs/runbooks/first-account.md`: the owner's steps in order, each with its check
- [ ] `make first-contact` makes each AWS adapter's cheapest read once and reports each answered
      or failed, typed; it refuses without credentials
- [ ] A test runs it over stubbed clients, one answering, one refusing, and with no credentials

---

### TASK-P12-009: proof and documents

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 13 |
| Delivers | The exit criteria, measured, and the record |
| Depends on | TASK-P12-001 to TASK-P12-008 |
| Estimate | S |

**Acceptance criteria.**

- [ ] Every exit criterion in spec section 13 met, each with its evidence
- [ ] FEAT-079 and FEAT-080 say what was built; ISS-182, ISS-250 and ISS-260 closed or updated;
      the register, `project_map.md` and the checkpoint updated, and `make check-docs` clean
