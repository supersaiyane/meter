# Runbook: deploy Meter for the first time

> **This procedure has never been executed.** It is derived from the Terraform
> in `infra/terraform/`, which passes `validate` and `fmt` and has never been
> applied to an AWS account, because no account has ever been provisioned. That
> is ISS-122, and it is the reason P0 is not signed off. Expect to find
> problems on the first run and expect to correct this file as you go. A
> procedure nobody has performed is a hypothesis, the same way an untested
> restore is.

## What you are building

Three stacks in two kinds of account.

| Stack | Runs in | Creates |
| --- | --- | --- |
| `management` | Your AWS Organizations management account | `FinOpsOrgReaderRole`, which Meter assumes to read the organization tree |
| `member` | The management account | A CloudFormation StackSet that puts `FinOpsCollectorRole` into every member account |
| `hub` | A dedicated account you choose | The service itself: VPC, Aurora, ECS, ALB, ECR, queue, scheduler |

Meter reads **many** accounts from **one** hub. There is no per account
installation, which is why onboarding an account later is mostly nothing. See
`onboard-account.md`.

## Before anything

**The order matters and it is not the obvious one.** The management and member
stacks trust a role in the hub account by **name**, not by ARN, so they can be
applied before the hub exists. Applying the hub first works too, but then you
have a service that cannot assume anything until the other two land, and its
first collection runs will fail with `AccessDenied` and look like a bug.

You need:

- Admin in the management account, and admin in the account that will host the hub.
- The organization id, `o-` followed by ten or more characters. `aws organizations describe-organization --query 'Organization.Id'`.
- The organizational unit ids the StackSet should reach. **Use the organization root** unless part of the organization is deliberately out of scope: the root covers accounts created later, which is what makes onboarding automatic.
- Terraform 1.9 or later and the AWS CLI.

### 1. Trusted access between Organizations and CloudFormation

The StackSet cannot deploy without it, and this is a one time switch in the
management account.

```bash
aws cloudformation activate-organizations-access --region us-east-1
```

This is ISS-002 and it is a decision somebody with organization admin has to
make, not something Terraform can do for you.

### 2. The state bucket

A stack cannot hold the state that describes it, so the bucket is created
outside Terraform. One per environment.

```bash
aws s3api create-bucket --bucket meter-terraform-state-dev \
  --region eu-west-1 --create-bucket-configuration LocationConstraint=eu-west-1
aws s3api put-bucket-versioning --bucket meter-terraform-state-dev \
  --versioning-configuration Status=Enabled
aws s3api put-public-access-block --bucket meter-terraform-state-dev \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
```

Versioning is not optional. It is the only thing that recovers a state file
somebody truncated.

There is no DynamoDB lock table. The backend uses S3 native locking,
`use_lockfile = true`.

### 3. The external id

The second half of the confused deputy defence, and at least 32 characters.
Generate it once, store it, and never put it in a tfvars file.

```bash
openssl rand -hex 32 | tee /dev/stderr | \
  aws secretsmanager create-secret --name meter/external-id \
  --secret-string file:///dev/stdin --region eu-west-1
```

Every stack below takes it with `-var` or `TF_VAR_external_id`. If it ever
appears in version control, rotate it: an ExternalId in a repository is not a
control.

## Apply the stacks

Set the external id once for the shell:

```bash
export TF_VAR_external_id="$(aws secretsmanager get-secret-value \
  --secret-id meter/external-id --query SecretString --output text)"
```

### 4. Management: the organization reader

Credentials for the **management account**.

```bash
cd infra/terraform/management
terraform init
terraform plan  -var-file=envs/dev.tfvars -var="hub_account_id=<hub account id>"
terraform apply -var-file=envs/dev.tfvars -var="hub_account_id=<hub account id>"
```

`envs/dev.tfvars` ships with `hub_account_id = "000000000000"`, which is a
placeholder. Override it or edit the file; a plan against the placeholder
creates a role nothing can assume.

Note the output. `FinOpsOrgReaderRole`'s ARN is what the hub needs.

### 5. Member: the collector role, everywhere

Still the management account. This is the StackSet, so it needs step 1 done.

```bash
cd ../member
terraform init
terraform apply -var-file=envs/dev.tfvars \
  -var="hub_account_id=<hub account id>" \
  -var="organization_id=o-xxxxxxxxxx" \
  -var='organizational_unit_ids=["r-xxxx"]'
```

`r-xxxx` is the organization root. Deploying to the root is deliberate: it
covers accounts created later.

This is slow. It creates one stack instance per account, and
`failure_tolerance_percentage` decides how many may fail before the whole
operation stops. Some will fail on the first run, usually accounts with an SCP
that forbids IAM role creation. Those accounts are then unreadable, and Meter
will say so on the accounts screen rather than omitting them.

### 6. Hub: the service

Credentials for the **hub account**.

```bash
cd ../hub
make tf-init  TF_ENV=dev
make tf-plan  TF_ENV=dev IMAGE_TAG=<a commit sha>
make tf-apply TF_ENV=dev IMAGE_TAG=<a commit sha>
```

`dev.tfvars` sets `org_reader_role_arn = ""`, which makes the organization
collector run against LocalStack instead of your management account. **Set it
to the ARN from step 4** or Meter will read a fake organization and report it
as real.

`image_tag` is never written into a tfvars file, because a stale default
quietly deploys the wrong image.

### 7. Images

The pipeline builds and pushes on every commit to the default branch. To do it
by hand, note that images must be `linux/amd64` or ECS reports `exec format
error`, which is constraint 13:

```bash
make build IMAGE_TAG=<sha>
make verify-platform
make push IMAGE_TAG=<sha>
```

### 8. Migrations

Run as a one off ECS task, before the service rolls:

```bash
scripts/deploy/run_migration_task.sh
```

Migrations are backward compatible by constraint 12, so old and new task
definitions run against the same schema during the rollout.

### 9. Prove it

```bash
curl https://<alb dns>/healthz
```

`degraded` on a fresh deployment is correct: nothing has collected yet. It
becomes `healthy` after the first successful run of every scheduled collector.
Then open the UI and check `/platform/freshness`, which is the screen that
tells you whether collection is actually happening.

## What is not automated, and will not be

| Step | Why a person does it |
| --- | --- |
| Trusted access between Organizations and CloudFormation | A one time organization wide grant. ISS-002 |
| The state bucket | A stack cannot hold its own state |
| The external id | A secret. Generating it in Terraform writes it to state |
| Choosing the hub account | An architectural decision, not configuration |

## Production differences

`prod.tfvars` refuses several things `dev.tfvars` allows, and the refusals are
in `alb.tf` rather than in documentation: production requires a
`certificate_arn`, so there is no HTTP only production, and it requires
`page_topic_arn` and `ticket_topic_arn`, so there are no alarms with no action
behind them.
