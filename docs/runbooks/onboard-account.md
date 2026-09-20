# Runbook: onboard an account, or a second organization

> Like `deploy.md`, this has never been executed. ISS-122.

## First, the question behind the question

"How do I point the UI at another account" usually means one of three different
things, and they have very different answers.

| What you mean | Answer |
| --- | --- |
| Another AWS account should appear in the estate Meter already reads | Usually nothing to do. See below |
| A different organization entirely, separate data, separate people | A second hub deployment |
| The same Meter, but a colleague should only see some accounts | Not a deployment change. Entitlements |

**Meter is not installed per account.** One hub reads every account the
organization reader and the StackSet reach. There is no per account
configuration in the UI, and adding one would be the wrong shape: the product's
whole claim is that it shows you the estate rather than a corner of it.

## A new account in an organization Meter already reads

If the StackSet targets the organization root, which is the default and the
recommendation in `deploy.md`, then **nothing**. CloudFormation puts
`FinOpsCollectorRole` into the account when it is created, the organization
collector picks it up on its next run, and it appears on the accounts screen.

Confirm rather than assume:

1. `/inventory/accounts` lists it. If not, the organization tree collector has
   not run since the account was created. Check `/platform/freshness`.
2. Its role health is `healthy`. If it says `not deployed`, the StackSet has
   not reached it yet. If it says `access denied`, the role exists and its
   trust policy is wrong, which is a different fix and a different owner. The
   screen keeps those apart on purpose.

If the StackSet targets specific organizational units rather than the root, an
account in an excluded unit is a manual step, which is the trade the
`organizational_unit_ids` variable documents.

### If the account will not read

The accounts screen names the cause. In order of how often it is the answer:

| Cause | Fix | Whose |
| --- | --- | --- |
| `not deployed` | The StackSet has not reached it. Re run the StackSet operation | Whoever owns the deployment |
| `access denied` | The trust policy names a different principal, or the external id does not match | Whoever owns the policy |
| `throttled` | Nothing. It retries with backoff | Nobody, unless it persists |
| `unknown` | The provider refused without saying which. Look at the run on `/platform/ingest` | Investigate |

An account that cannot be read is still listed, with its cause. Meter does not
omit it, because a shorter list of accounts reads as a smaller estate and that
is the failure the whole product is built against.

## A separate organization

Deploy a second hub. Not a second tenant inside the first one: the tenant
boundary is enforced, but the *collection* boundary is the organization reader
role, and one hub has one of those.

What must differ:

- A different hub account.
- A different state key. `envs/<env>.backend.hcl`, and do not reuse `hub/dev.tfstate`.
- Its own external id. Sharing one across organizations makes it a shared secret between parties who have no relationship.
- Its own `organization_id` and organization reader role in that organization's management account.

Everything else is the same procedure as `deploy.md`.

## The same Meter, and a person who should see less

This is entitlements, not deployment, and no infrastructure changes.

Scope is enforced in two places, a request dependency and a repository guard,
so a route that forgets the dependency still cannot read out of scope data.
That is constraint 3, and it is why the answer here is configuration rather
than a separate installation.

In development the entitlement comes from `local-auth.yaml`:

```yaml
users:
  - subject: analyst@example.local
    display_name: An Analyst
    email: analyst@example.local
    tier: analyst
    is_global: false
    accounts:
      - "111122223333"
```

`is_global: true` sees the whole organization. `is_global: false` sees exactly
the listed accounts and nothing else.

In a deployed environment this comes from the identity provider, which is
ADR-0008 and OPEN-01, and **is not built**: `METER_IDENTITY_PROVIDER` accepts
`local_config` only, and the application refuses to start in production with
it. So a deployed multi user Meter is not currently possible, and that is a gap
rather than a configuration step.

## What a scoped user sees

Not a smaller list presented as the whole. Every response carries
`scope_coverage`, and the trust strip reads `Showing 2 of 5 accounts`, because a
partial view presented as a total is the same failure as a missing account.
