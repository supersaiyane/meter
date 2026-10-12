# FEAT-079: Ingest that runs, one composition and the dispatcher and worker processes

| Field | Value |
| --- | --- |
| Sub project | P12 |
| Status | In build |
| Specification | [P12 spec](../specs/2026-10-12-p12-deployment-readiness-design.md), sections 5.1 to 5.3 and 5.6 |
| Tasks | TASK-P12-001 to TASK-P12-005 and TASK-P12-008 |

## What it does

Assembles every collector the worker runs into one registry, built per unit of work, and runs it:
a dispatcher that publishes each tenant's due units to the queue and exits, and a worker that
consumes the queue and runs them. A deployment binds the collectors to AWS adapters; the local
stack binds the same collectors to the fakes and runs end to end with no account. `make
first-contact` proves each AWS adapter's first real call once an account is connected.

## Why it exists

Nothing in production assembled the collectors, ISS-182, and the dispatcher and worker images
start a module with no entry point and exit, so a deployed Meter would collect nothing however
complete its collectors are.

## What is already known

34 collectors are scheduled (measured on 2026-10-12): 33 run in the worker, six of them the
retention jobs, and `report_schedules` runs in the API, where it is already wired. The worker
already claims, runs and records a unit, and resolves each account's session through the
credential broker; what was missing is the composition that builds the collectors and the
processes that call the worker. Whether the processes run on fakes before an account was OPEN-28,
answered 2026-10-12 as fakes by a setting and amended the same day: ADR-0022 keeps the fakes out of
the runtime image, so they run only in the local stack and no setting is needed.

## How it works

Built so far: the two compositions, TASK-P12-001, the AWS binders, TASK-P12-002, and the queue,
TASK-P12-003.

- `finops_ingest/composition.py` declares a `Binding` per collector: its name, its scope, and a
  builder that constructs it from one unit's context. `compose` registers each binding behind a
  runner that builds the collector for the unit in hand and runs it, then adds the six retention
  jobs, which need nothing built. `production_registry` is the registry a deployment runs.
- Six collectors are judged per account in one Region (`PER_ACCOUNT`); the rest are organization
  wide, run once per tenant. Both compositions take their scope from the same function, and a
  test holds them equal.
- In a deployment the six collectors that read only Meter's own tables (commitment actions, cost
  anomaly, the score, realized savings, the savings ledger, team digests) are built for real, and
  17 more are built from their AWS adapters, `finops_ingest/aws_bindings.py`: per account ones on
  the session the worker assumed, organization wide ones on the hub's own credentials, a member
  account through the credential broker, and Budgets, Invoicing, spot prices and Savings Plans
  rates through the relay. The payer is the account in the org reader role's ARN. Four cannot be
  built for AWS yet and fail each run typed: three ports with no adapter, ISS-240, and
  `query_audit`, ISS-272.
- `finops_providers/aws/reach.py` makes every client on the adapter's first call, so building a
  collector makes none, and a failure arrives where the adapter types it.
- `finops_ingest/sqs.py` carries units between the processes: `SqsPublisher` sends one versioned
  JSON message per unit and refuses one it already sent in this dispatch, and `SqsConsumer`
  long polls up to ten, reports each unit with how often it has been received, and deletes what
  was settled. The hub's queue is a standard queue, so a unit sent twice by two dispatches, or
  delivered twice, is made free by the ledger's claim on the same key.
- `finops_fakes/composition.py` binds the same 27 collectors from the fakes, on a clock it is
  handed rather than one it reads, and hands a per account collector only the candidates of the
  unit's own account, as the demo seed does. `fake_registry(clock)` is what the local stack's
  entry points will call, TASK-P12-004.

## Failure behaviour

- A collector that cannot be built for AWS raises `Misconfigured` on every run, carrying the
  unit's scope key and a detail naming the issue that says why. A read whose setting is empty,
  `METER_RELAY_FUNCTION_NAME`, `METER_S3_BUCKET`, `METER_CONFIG_AGGREGATOR`, or an org reader
  setting that is not a role ARN, fails the same way naming the setting. The worker records it
  as a typed failure in `sync_error`, so it shows on the freshness screen and never as zero.
- A builder that raises fails only its own unit; the worker's per unit isolation is unchanged.
- A message the worker cannot decode, including one of a version it does not read, is logged with
  its id and receive count and left on the queue, so the redrive moves it to the dead letter queue
  after the hub's three receives. A delete SQS refuses is logged and returned; the unit comes back
  and its claim makes the second run a skip.
- A collector missing from either composition, or bound twice, fails
  `tests/ingest/test_composition.py`, which holds both to the collectors the schedule runs in the
  worker.

## Security considerations

- No production package imports `finops_fakes`, enforced by the import contract of ADR-0022, and
  the runtime images do not copy it. A deployed process therefore cannot be switched onto fakes by
  any setting, because there is no setting.
- The binders add no credential path. An account scoped collector reads on the session the
  worker resolved for that unit; an organization wide one reaches a member account through the
  same credential broker, so it assumes the role the worker would have. Nothing is written.
- A role the worker cannot assume fails the account health unit before the collector runs, so
  `role_health` keeps its last value, ISS-273.

## Interface

- `finops_ingest.composition.production_registry() -> CollectorRegistry`
- `finops_ingest.composition.production_bindings() -> tuple[Binding, ...]`
- `finops_ingest.composition.worker_collectors() -> frozenset[str]`
- `finops_fakes.composition.fake_registry(clock) -> CollectorRegistry`
- `finops_fakes.composition.fake_bindings(clock) -> tuple[Binding, ...]`
- `finops_ingest.aws_bindings.AWS_BUILDERS` and `UNBUILT`
- `finops_ingest.sqs.SqsPublisher(client, queue_url)` and `SqsConsumer(client, queue_url)`, message
  version 1
- Settings `relay_function_name` (`METER_RELAY_FUNCTION_NAME`) and `config_aggregator`
  (`METER_CONFIG_AGGREGATOR`), empty by default

## Not doing

- No `METER_PROVIDERS` setting. The entry point chooses the composition.
- No fake in a deployed environment before an account is connected; a deployment with no account
  shows each collector's typed failure instead.
- No adapter for the ISS-240 ports in this release; those collectors stay failing typed.

## Status of this document

In build. TASK-P12-001 built the two compositions, TASK-P12-002 the AWS binders and TASK-P12-003
the queue on 2026-10-12; the entry points and the local stack end to end follow in TASK-P12-004
and TASK-P12-005.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P12.
