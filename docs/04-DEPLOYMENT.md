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

Workers run in private subnets with VPC interface endpoints for STS, SQS,
Secrets Manager, Cost Explorer and CloudWatch Logs, plus a gateway endpoint for
S3. No NAT Gateway.

**Correction, 2026-08-23.** This was previously justified on cost, and that
justification was wrong. Working the numbers for the cost estimate below
produced this:

| Option | Fixed per month | Per GB | At 300 GB | At 2,000 GB |
| --- | --- | --- | --- | --- |
| NAT Gateway | 33 USD | 0.045 | **46 USD** | 123 USD |
| 6 interface endpoints across 2 AZs | 88 USD | 0.010 | 91 USD | **108 USD** |

**NAT is cheaper below roughly 1,560 GB per month**, and Meter's egress is
nowhere near that. The traffic is AWS API calls returning small JSON, so a few
hundred gigabytes a month is the realistic figure even at 300 accounts.

The decision stands, on a different and honest basis:

1. **Traffic never traverses the public internet.** In a financial services
   environment that is worth more than 45 USD a month, and it is a statement
   that can be made to a reviewer without qualification.
2. **No single point of failure.** A NAT Gateway is one, per availability zone,
   and a second one for redundancy erases most of the cost advantage anyway.
3. **No egress path at all** means a compromised worker container cannot reach
   an arbitrary host. That bounds the damage in the threat model, boundary 5.

Recorded as ISS-080. The lesson generalises: a decision justified on cost
should have the arithmetic next to it, or it is a preference wearing a
justification.

## What it costs to run

Estimates, not quotes. Region `eu-west-1`, on demand, list price, at
2026-08-23. **Modelled, not measured**, which is exactly the label this product
applies to everyone else's numbers.

The assumptions are stated so a reader can disagree with a number rather than
with the total.

### P0, no cost data yet

| Item | Assumption | USD per month |
| --- | --- | --- |
| Fargate, API | 2 tasks, 0.5 vCPU, 1 GB | 36 |
| Fargate, worker | 1 task average, scales 0 to 4 on queue depth | 36 |
| Fargate, web | 2 tasks, 0.25 vCPU, 0.5 GB | 18 |
| Aurora Serverless v2 | 2 ACU average, 100 GB storage | 185 |
| Application Load Balancer | Low LCU | 26 |
| VPC interface endpoints | 6 services, 2 AZs, plus 300 GB | 91 |
| S3 | Raw exports and reports | 5 |
| SQS | Around 2 million requests | 1 |
| Secrets Manager | A handful of secrets | 2 |
| ECR | 5 GB with lifecycle policies | 1 |
| Cost Explorer | 1 grouped request daily | 3 |
| CloudWatch, Meter's own logs and metrics | | 15 |
| **P0 total** | | **around 420** |

Roughly flat between 50 and 300 accounts. P0 collects metadata, and the tree
plus health check for 300 accounts is minutes of Fargate time.

### Adding P1 to P3

| Item | At 50 accounts | At 300 accounts |
| --- | --- | --- |
| Athena, CUR extract and load | 10 | 60 |
| Aurora, larger rollups | +40 | +150 |
| CloudWatch `GetMetricData`, rightsizing | 15 | 90 |
| Fargate, longer sweeps | +20 | +80 |
| **Subtotal** | **around 85** | **around 380** |
| **Running total** | **around 505** | **around 800** |

### The number that dominates everything else

| Item | At 300 accounts |
| --- | --- |
| **AWS Config, all resource types, continuous** | **1,000 to 4,000** |
| AWS Config, periodic for stable types, continuous for critical only | 200 to 600 |

Config is charged per configuration item recorded. Recording everything, in
every account, in every region, costs several times the rest of the platform
combined. This is ISS-012, and the mitigation is already decided: periodic
recording for stable resource types, continuous only for critical ones.

**Anyone enabling Config organization wide without that mitigation will
multiply the platform's cost by five.** It is called out here rather than only
in the P4 roadmap entry, because whoever turns it on will be reading this
document and not that one.

### Honest reading

At 300 accounts with P1 to P3 and Config mitigated, roughly **1,000 to 1,400
USD per month**. Against the 100,000 USD in one week that triggered this
project, that is under a day of the failure it prevents.

These figures are re measured, not re estimated, once `platform_cost` has data.
FEAT-008 exists so the estimate can be checked against the bill, and the
difference is worth publishing.

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
