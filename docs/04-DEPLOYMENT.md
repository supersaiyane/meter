# Deployment

Last updated: 2026-08-23
Update trigger: any change to the pipeline, the images, or the Terraform layout

## The path from commit to running service

```
developer push
      |
      v
GitLab                verify: lint, writing rules, tests, terraform validate
      |
      v
Kaniko build          three images: meter-api, meter-worker, meter-web
      |               tagged with the short commit SHA and the branch slug
      v
Amazon ECR            one repository per image, plus a shared cache repository
      |
      v
Terraform plan        hub stack, image_tag passed in as a variable
      |
      v
Terraform apply       writes a new ECS task definition revision
      |
      v
ECS Fargate           rolling replacement behind the ALB, health check gated
```

## Why Terraform performs the deploy

The obvious alternative is `aws ecs update-service --force-new-deployment`
after the image push. It is rejected.

If the pipeline mutates the ECS service directly, Terraform's recorded state no
longer matches reality. The next `terraform apply`, for an unrelated change,
silently reverts the running image to whatever tag the state file remembers.
That failure is intermittent, hard to diagnose, and happens at the worst
possible moment.

So Terraform owns the task definition, and `image_tag` is a variable. One
system owns the desired state. The deploy is `terraform apply`.

## Images

| Image | Dockerfile | Base | Runs as | Port |
| --- | --- | --- | --- | --- |
| `meter-api` | `docker/Dockerfile.api` | `python:3.12-slim` | uid 10001, non root | 8000 |
| `meter-worker` | `docker/Dockerfile.worker` | `python:3.12-slim` | uid 10001, non root | none |
| `meter-web` | `docker/Dockerfile.web` | `nginx:1.27-alpine` | `nginx` user | 8080 |

Every image is multi stage, so no build toolchain reaches the runtime layer.
No credential is baked into any layer. AWS credentials come from the ECS task
role at runtime.

`meter-worker` carries both the dispatcher and the worker process, selected by
the `METER_ROLE` environment variable. One artifact is promoted through
environments rather than two that could drift apart.

## Platform: the images must be amd64

The target servers are `linux/amd64`. A build on an Apple Silicon machine
produces `linux/arm64` by default, and **`docker push` does not convert it**.
The image lands in the registry as arm64, and the amd64 host fails at start
with `exec format error`, which reads like a corrupt binary rather than a wrong
architecture and costs an afternoon to diagnose.

Four controls, because one is not enough when the failure is this silent.

| Control | Where |
| --- | --- |
| `FROM --platform=${TARGETPLATFORM}` on every runtime stage | the Dockerfiles |
| `FROM --platform=${BUILDPLATFORM}` on every builder stage, so compilation runs natively rather than emulated | the Dockerfiles |
| `--platform linux/amd64` on every build command | `make build`, `make buildx-push` |
| `make verify-platform`, which inspects the built image and fails on a mismatch | runs automatically after `make build` and before `make push` |

The pipeline adds a fifth: after the push, it reads the architecture back out
of the **registry manifest** and fails the scan stage on a mismatch. That is
the only check that sees what actually reached the registry rather than what
was intended locally.

Cross platform builds need buildx:

```bash
make buildx-setup
```

Each image also carries an `io.meter.platform` label, so an artifact repository
that inspects labels rather than manifests can read the architecture directly.

To target a different architecture, override once:

```bash
make build PLATFORM=linux/arm64
```

## Health checks

The API health route reports database reachability and ingestion freshness, not
just process liveness. A container that has started but cannot see its data is
reported unhealthy rather than quietly serving stale numbers. This matters more
here than in a typical service, because the product's entire value is that its
numbers can be trusted.

`aws ecs wait services-stable` gates the pipeline on the rollout completing, so
a failing deploy fails the pipeline instead of appearing to succeed.

## Migrations

Migrations run as a one off ECS task, on the same image, before the service
rollout.

**Migrations must be backward compatible.** During a rolling deploy the old and
new task definition revisions run against the same schema at the same time. The
rule that follows: add a column, deploy code that writes both, backfill, then
remove the old column in a later release. Never rename or drop in the same
release that stops using the thing.

## Authentication from GitLab to AWS

GitLab OIDC. The pipeline mints a JSON Web Token, AWS trades it for a
short lived session through `AssumeRoleWithWebIdentity`. No long lived AWS
access key is stored as a CI variable.

The trust policy on `AWS_DEPLOY_ROLE_ARN` restricts the subject claim to this
project and to the specific branches allowed to deploy.

## Why Kaniko rather than docker-in-docker

Docker-in-docker needs a privileged runner. Most platform teams will not
approve one, and they are right not to. Kaniko builds in userspace, so the
pipeline runs on a standard shared runner.

## Terraform layout

```
infra/terraform/
├── hub/          the platform itself. VPC, ECS, Aurora, SQS, S3,
│   ├── envs/     EventBridge, ALB, ECR, hub role. Per environment
│   │             backend config and tfvars
├── member/       the FinOpsCollectorRole StackSet, service managed,
│                 automatic deployment to the organization root
└── management/   the FinOpsOrgReaderRole in the management account
```

Three root modules because they have three different credential requirements
and three different change cadences. `hub` changes on most releases. `member`
changes only when a collector needs a new permission. `management` changes
almost never and requires management account access.

## Environments

| Environment | Trigger | Approval |
| --- | --- | --- |
| `dev` | Automatic on the default branch | None |
| `prod` | Manual job on the default branch | Manual, and the plan artifact must be reviewed |

Production deploys apply the plan artifact produced earlier in the same
pipeline. Applying a freshly generated plan would mean approving one thing and
applying another.

## Network

Workers run in private subnets with VPC interface endpoints for STS, S3, SQS,
Secrets Manager, Cost Explorer and CloudWatch Logs, rather than a NAT Gateway.

A NAT Gateway is billed per hour and per gigabyte processed. This workload is
chatty across hundreds of accounts, so interface endpoints are cheaper here and
keep the traffic off the public internet. Recorded because it looks like an
over engineered choice until the data processing charge appears on the bill.

## Local development

```bash
make setup
make up
```

`docker-compose.yml` runs PostgreSQL, LocalStack, the API, the dispatcher, the
worker and the frontend.

**What LocalStack is doing.** It emulates the AWS APIs Meter calls: STS, SQS,
S3, Secrets Manager, Organizations, Cost Explorer, Logs and CloudWatch. Without
it, running the ingestion loop locally needs a real AWS account, real
credentials on every developer machine, and it bills for every Cost Explorer
and `GetMetricData` call. For a product whose purpose is stopping runaway cloud
spend, a development loop that quietly bills per keystroke is the wrong default.

**What LocalStack is not.** It is not AWS. Community edition does not enforce
IAM, its pagination and throttling behaviour differ, and its error codes are
not always the real ones. It proves the plumbing works. It does **not** prove
the AWS semantics are right.

Correctness against real AWS behaviour is covered by `moto` and the port
contract suite in `tests/contract/`, which is why that suite is parameterised
over providers and runs against both the fake and the AWS adapter. Never
conclude "it works" from LocalStack alone, and never test a permission boundary
against it.

A second profile holds one shot scanners:

```bash
make scan-local     # build, then scan with the compose security profile
```

They do not start with `make up`. Scanners are jobs, not services, and a
container cannot gate an image that already exists and is already running. See
`docs/05-SECURITY.md`, "Why compose is not a gate".

Local is not production. `docker-compose.yml` is never used to deploy anything.

## Required CI variables

| Variable | Purpose | Type |
| --- | --- | --- |
| `AWS_ACCOUNT_ID` | Builds the ECR registry hostname | Variable |
| `AWS_DEPLOY_ROLE_ARN` | The role GitLab OIDC assumes | Variable |
| `AWS_REGION` | Defaults to `eu-west-1` | Variable |

No secret variables. That is the point of OIDC.

## Current state

The pipeline, the Makefile, the Dockerfiles and the compose file are written
against the module layout in the P0 specification. They will not build until
P0 application code exists. This is deliberate: the deployment contract is
fixed before the code, so the code is written to fit a known target rather than
the deployment being retrofitted to whatever the code turned out to be.

Tracked as CHG-0003 in `INDEX.md`.
