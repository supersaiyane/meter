# FEAT-080: Deployed settings from SSM Parameter Store, and a pipeline that applies its own plan

| Field | Value |
| --- | --- |
| Sub project | P12 |
| Status | Planned |
| Specification | [P12 spec](../specs/2026-10-12-p12-deployment-readiness-design.md), sections 5.4 and 5.5 |
| Tasks | TASK-P12-006 and TASK-P12-007 |

## What it does

Puts every setting a deployed task needs in SSM Parameter Store, one parameter per setting under
`/meter/<env>/`, injected into each task definition at start, with the secret ones created by
Terraform with a placeholder and set by the owner. And makes each deploy job apply the plan made
for its own environment.

## Why it exists

The hub's task definitions pass 6 of the settings the API requires, so a deployed API refuses to
start, ISS-250; and the deploy jobs share one plan file across two environments, so a deploy may
apply the wrong plan or none, ISS-260.

## What is already known

`.env.example` is the one complete description of the settings and `make up` holds a local `.env`
to it; nothing held a deployed environment to it. Where deployed settings live was OPEN-29,
answered 2026-10-12: SSM Parameter Store.

## How it works

Built so far: the settings, TASK-P12-006.

- `infra/terraform/hub/settings.tf` makes one SSM parameter per setting under `/meter/<env>/`
  from three sources: the names the stack derives from what it creates, such as the queue URL,
  the buckets, the relay and the database URL; the committed `settings` map in
  `envs/<env>.tfvars`; and the secret ones, SecureString parameters made with a placeholder.
- The api, worker and dispatcher task definitions read every parameter through the container's
  `secrets`, which the execution role resolves at start. A setting that is empty on purpose
  cannot be a parameter, because SSM refuses an empty value, so it reaches the task as an empty
  environment value from the same map.
- The database URL names the host and the user and no password. Each task is given the password
  RDS manages as `PGPASSWORD`, from the managed secret's `password` key, and libpq reads it.

## Failure behaviour

- A setting added to the model without a parameter fails `tests/scripts/test_deployed_settings.py`,
  which holds the three sources to every field of `Settings` for each environment.
- A task whose signing key is still the placeholder refuses to start, naming the setting and the
  runbook step that sets it.
- A production environment cannot start yet: the local identity provider is refused in prod and
  no other is built, ISS-280.

## Security considerations

- The execution role reads `/meter/<env>/*` and nothing wider, so one environment's task cannot
  be started on another's parameters. The running process holds no permission to read them.
- No secret value is in git or the Terraform state: the secret parameter's value is ignored after
  creation and the database password is never a parameter.
- RDS rotates the managed password every seven days by default, and a password injected at start
  does not follow it, ISS-279.

## Interface

- SSM parameters `/meter/<env>/METER_*`, one per setting
- Terraform variable `settings`, a map of `METER_` name to value, per environment
- `finops_core.config.UNSET_SECRET`, the placeholder a process refuses

## Not doing

- No settings file baked into an image, and no parameter read by application code at run time.
- No rotation handling in this task, ISS-279.

## Status of this document

In build. TASK-P12-006 built the deployed settings on 2026-10-12; each deploy applying its own
plan follows in TASK-P12-007.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P12.
