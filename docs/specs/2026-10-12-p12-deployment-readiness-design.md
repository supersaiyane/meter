# P12 Deployment readiness: design specification

Date: 2026-10-12
Status: Approved by the owner on 2026-10-12 with OPEN-28 and OPEN-29 answered, in build. Chosen the same day as the next priority, ahead of the security and correctness highs and the rest of `next-in-scope.txt`
Sub project: P12
Features: FEAT-079, FEAT-080
Depends on: P0 to P11 delivered against fakes. Proof against a real estate waits on ISS-002, an AWS account
Supersedes: nothing

## 1. Purpose

Every sub project from P1 to P11 is delivered against fakes and the seeded demo, and a deployed
Meter would still collect nothing. Nothing in production assembles the collectors, ISS-182; the
dispatcher and the worker images start a module with no entry point and exit; and the API's task
definitions pass 6 of the settings it requires, ISS-250, so it refuses to start. P12 makes the
platform run outside its tests: one composition of every scheduled collector, a dispatcher and a
worker that actually run, the deployed settings in one place, and a pipeline that applies the plan
it made. It ends at the edge of what can be done without an account, with the owner's steps for
the first one written down and a check that proves each adapter's first real call.

## 2. Definition of done

- One composition registers every collector the worker runs, with AWS adapters for a deployment
  and fake adapters for the local stack, and a test fails when one is missing from either.
- `python -m finops_ingest.dispatcher` enumerates what is due and publishes it to the queue, and
  `python -m finops_ingest.worker` consumes the queue and runs each unit, each a real process.
- The local stack, `make up`, runs a collector end to end on fakes: dispatched, queued, claimed,
  run and recorded in `ingest_run`, proved by a test.
- Every setting a deployed task needs reaches it from SSM Parameter Store, held to the settings
  model by a test.
- The deploy jobs apply the plan made for their own environment.
- The owner's steps for the first account are a runbook, and `make first-contact` reports which
  adapters made their first real call and which failed, typed.

## 3. Out of scope

- Connecting an AWS account, planning or applying Terraform, and the snapshot restore: the owner's,
  ISS-002, ISS-122 and ISS-111, prepared here and done there.
- Choosing and adding a git remote, OPEN-30, and so the first pipeline run, ISS-179.
- Adapters for the ports that have a fake and no AWS adapter, ISS-240: their collectors are
  composed and refuse in AWS mode with a typed error rather than running on a fake.
- The security and correctness highs, which follow as their own sub project.

## 4. The gap, measured on 2026-10-12

- `finops_ingest/registry.py` declares 34 scheduled collectors (measured): 33 run in the worker, and
  `report_schedules` runs in the API, where it is already wired. `CollectorRegistry.register` is
  called by tests and by `register_retention`, and by nothing that runs in a deployed process.
- `docker/Dockerfile.worker` runs `python -m finops_ingest.worker`, and the hub's scheduler runs
  `python -m finops_ingest.dispatcher`; neither module has a `__main__` block, so both exit at once,
  locally and in AWS.
- Each collector takes its adapters when constructed, and an AWS adapter is bound to one account's
  session. The worker already resolves that session through the credential broker,
  `finops_providers/aws/credentials.py`, and passes it in the collector's context.
- `infra/terraform/hub/ecs.tf` passes 6 settings; ISS-250 counted 68 required settings reaching no
  deployed task on 2026-10-05, and the settings model has grown since.
- `.gitlab-ci.yml` writes one `tfplan` for both environments of its plan matrix, ISS-260.

## 5. Decisions

### 5.1 One composition for a deployment, one for the local stack, OPEN-28

Each collector is registered with a builder that constructs it for one unit of work, from that
unit's context. `finops_ingest/composition.py` holds the bindings a deployment runs, with AWS
adapters built on the unit's session, and never reaches a fake. `finops_fakes/composition.py` binds
the same collectors from the fakes, on a clock it is handed, and the local stack reaches it
through entry points of its own from a development image. The entry point decides, so no setting
can switch a deployed process onto fakes. A collector that reads only Meter's own tables is bound
for real in both; one whose AWS adapter is not yet bound, ISS-240 or TASK-P12-002, fails each run
typed as Misconfigured, naming what it lacks, so it appears in `sync_error` and on the freshness
screen rather than nowhere.

Amended 2026-10-12, TASK-P12-001. The owner answered OPEN-28 with fakes by a setting, which as
first written would also have run a deployed environment on fakes before an account. ADR-0022 keeps
the fakes out of the runtime image, and the owner chose the same day to keep it so: fakes run only
in the local stack, and `METER_PROVIDERS` is not needed.

### 5.2 Two processes with entry points

The dispatcher is a one shot process, run on the schedule the hub's EventBridge rule already sets:
for each tenant it reads `due_collectors`, enumerates the units and publishes them, then exits. The
worker is a long running process: it long polls the queue, hands each batch to `Worker.handle_batch`,
deletes what succeeded, leaves a failure for the queue's redrive, and stops cleanly on SIGTERM
between batches, so an ECS deploy never kills a unit halfway through its transaction.

### 5.3 The queue is SQS

A publisher and a consumer over SQS through boto3, the queue named by `queue_url`. Locally the
queue is LocalStack's, already in `docker-compose.yml`; in tests it is moto's. The dead letter
queue the hub declares receives what fails more than the worker's attempt limit.

### 5.4 Deployed settings live in SSM Parameter Store, OPEN-29

One parameter per setting under `/meter/<env>/<NAME>`, injected into each task definition through
the container's `secrets` with `valueFrom`, which ECS resolves at start. The values that are not
secret are a committed Terraform map per environment; the secret ones are SecureString parameters
Terraform creates with a placeholder and never manages the value of, so no secret reaches git or
the Terraform state, and the owner sets them once. The task execution role reads only its own
environment's path. A test holds every field of the settings model to a parameter, so a setting
added without one fails the build, which is the drift ISS-250 describes. Answered by the owner on
2026-10-12: SSM Parameter Store.

### 5.5 Each deploy applies its own plan

The plan job writes one plan file per environment, and each deploy job needs the plan job of its
own environment. A test reads `.gitlab-ci.yml` and fails if two jobs share a plan path or a deploy
needs a job that publishes no plan. ISS-260.

### 5.6 The first account

`docs/runbooks/first-account.md` lists the owner's steps in order, each with its check: trusted
access between Organizations and CloudFormation, the organization reader role, the member StackSet,
a `terraform plan` of each stack, ISS-122, the Aurora snapshot restore, ISS-111, and the first
pipeline run, ISS-179. `make first-contact` then makes each AWS adapter's cheapest read once,
against one account and Region the owner names, and reports each as answered or failed with its
typed cause; it refuses to run without credentials rather than reporting nothing.

## 6. Data model

No table changes. The composition, the processes and the settings are configuration and code.

## 7. Collectors and cadence

No new collectors. All 33 scheduled collectors, and the retention jobs, become reachable from the
deployed processes for the first time.

## 8. Interface

- `finops_ingest.composition.production_registry` and `finops_fakes.composition.fake_registry`.
- `python -m finops_ingest.dispatcher` and `python -m finops_ingest.worker`.
- `make first-contact`, and `docs/runbooks/first-account.md`.

## 9. Testing

The composition is tested in both modes for every scheduled collector. The queue publisher and
consumer are tested under moto. The processes are tested by running their entry points against
moto's queue and the test database. The local stack is proved end to end by a test that dispatches
and runs one collector through the compose services. The settings test reads the Terraform and the
settings model. The pipeline test reads `.gitlab-ci.yml`.

## 10. Risks

- AWS mode is proved only to the point of construction until an account exists: every binder is
  built and typed, and none has made a call, which is ISS-002 and ISS-216.
- A worker killed between a unit's transaction and its message deletion reruns the unit; the run
  ledger's claim makes the rerun a skip, which is the guarantee this relies on.
- A placeholder secret left unset makes a task fail at start; `make first-contact` and the runbook
  check every secret parameter has been set.

## 11. Open questions

- OPEN-28: what the processes run against before an account. Answered 2026-10-12, fakes by a setting.
- OPEN-29: where deployed settings live. Answered 2026-10-12, SSM Parameter Store.
- OPEN-30: which git host takes the remote, which decides where the first pipeline run happens,
  ISS-179. Open, the owner's.

## 12. Features delivered

- FEAT-079: ingest that runs, one composition and the dispatcher and worker processes.
- FEAT-080: deployed settings from SSM Parameter Store, and a pipeline that applies its own plan.

## 13. Exit criteria

1. Every scheduled collector is in the composition in both modes, and one runs end to end on the
   local stack, dispatched, queued, claimed, run and recorded.
2. Every setting reaches a deployed task from SSM Parameter Store, held by a test.
3. Each deploy job applies the plan of its own environment, held by a test.
4. The first account's steps are a runbook, and `make first-contact` refuses without credentials and
   reports each adapter's first call, typed, with them.
