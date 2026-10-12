# Runbook: the first account

The owner's steps to connect Meter to its first AWS account, in order, each with the check that
says it worked. TASK-P12-008, FEAT-079, P12 spec section 5.6. The commands for each step are in
[deploy.md](deploy.md); this file is the order, the checks, and what is known to stop you.

> **Nothing here has been done yet.** No account has been connected, ISS-002, no stack has been
> applied, ISS-122, and no pipeline has run, ISS-179. Expect each step to find something, and
> record what it finds in `tasks/ISSUES.md` as it happens.

## Known to stop you before you start

| Issue | What it stops | What to decide |
| --- | --- | --- |
| ISS-280 | Any deployed API authenticating anyone; prod does not start | Which identity provider |
| ISS-283 | Any deployment applying its migrations; a first deploy has an empty schema | How a deployment migrates |
| ISS-279 | The tasks keeping a database connection past the first password rotation | How the password is used |

The collectors can be proved without these: `make first-contact` needs no API and no schema.

## The steps

| # | Step | Where | Check |
| --- | --- | --- | --- |
| 1 | Trusted access between Organizations and CloudFormation | deploy.md, step 1 | `aws organizations list-aws-service-access-for-organization` lists `member.org.stacksets.cloudformation.amazonaws.com` |
| 2 | The state bucket and the external id | deploy.md, steps 2 and 3 | `aws secretsmanager describe-secret --secret-id meter/external-id` answers in the hub account |
| 3 | The organization reader role | deploy.md, step 4 | `aws iam get-role --role-name <the reader role>` answers in the management account |
| 4 | The member StackSet | deploy.md, step 5 | `aws cloudformation list-stack-instances --stack-set-name <the member stack set>` shows every instance `CURRENT` |
| 5 | A plan of each stack, read before any apply, ISS-122 | deploy.md, steps 4 to 6 | Each `terraform plan` ends with no error and creates only what the step says |
| 6 | The hub, and its settings | deploy.md, step 6 | `aws ssm get-parameters-by-path --path /meter/dev/ --query 'length(Parameters)'` answers, and the signing key is set |
| 7 | The settings the hub cannot derive | `infra/terraform/hub/envs/dev.tfvars` | `org_reader_role_arn` is the ARN from step 3, and the CUR prefix and table name are the export's |
| 8 | First contact | this file, below | Every read answered |
| 9 | The restore drill, ISS-111 | [restore.md](restore.md) | `make restore-drill` passes, then the Aurora snapshot restore in that file |
| 10 | The first pipeline run, ISS-179 | `.gitlab-ci.yml` | Every job up to `deploy:dev` passes; record what it found |

## First contact

With credentials for the hub account and `AWS_REGION` set to the hub's Region:

```bash
make first-contact ENV=dev ACCOUNT=<a member account id> REGION=<a Region it uses>
```

It makes each AWS read a collector depends on once, through the same path the deployed worker
takes, and prints one line each:

| Outcome | Meaning |
| --- | --- |
| `answered` | The read worked |
| `AccessDenied` | The role or its policy refuses it; the line names the role and the call |
| `NotOptedIn` | The service is not enabled in that account or Region |
| `Throttled` | Try again; a first contact makes one call each |
| `Unreachable` | No route to the endpoint: the hub's network or an endpoint is missing |
| `not tried` | A setting it needs is empty, and the line names it |

It exits 0 only when every read answered, 1 otherwise, and 2 when there are no credentials, which
it refuses rather than report every read as failed. It writes nothing. Cost Explorer charges USD
0.01 a request (modelled from AWS's published price), and the four relayed reads start one Lambda
invocation each.

A read that fails here fails the same way in the worker, with the same typed cause on the
freshness screen, so fix it here first. When every line says answered, the account is connected:
record the date and the output under ISS-002.
