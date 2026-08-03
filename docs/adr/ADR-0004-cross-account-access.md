# ADR-0004: Cross account access by StackSet deployed role with a curated policy

Date: 2026-08-23
Status: Accepted

## Context

Meter must read from every account in the Organization. Two questions: how the
role gets into each account, and what the role is allowed to do.

The requirement says "scan if any child is available". Scanning for child
accounts is unnecessary. AWS Organizations already holds the exact tree.

## Decision

Three roles.

| Role | Location | Trust | Grants |
| --- | --- | --- | --- |
| `FinOpsHubTaskRole` | hub account | ECS tasks | AssumeRole into member roles, plus S3, SQS, KMS, Secrets Manager |
| `FinOpsCollectorRole` | every member account | hub role, plus ExternalId, plus `aws:PrincipalOrgID` condition | curated read only policy |
| `FinOpsOrgReaderRole` | management account | hub role | `organizations:List*` and `Describe*` only |

`FinOpsCollectorRole` is deployed by a service managed CloudFormation StackSet
with automatic deployment to the organization root. A newly vended account is
onboarded with zero human steps.

The member policy is a curated list of roughly 40 actions. It is explicitly
not the AWS managed `ReadOnlyAccess` policy.

## Consequences

Positive.

- Onboarding is automatic and cannot be forgotten.
- The organization tree comes from the Organizations API rather than
  discovery, so the parent to child map is exact rather than inferred.
- The curated policy passes a security review. It grants no data plane read.

Negative.

- Adding a new collector often requires a policy change, which means a
  StackSet update across every account. Mitigated by grouping expected future
  actions into the initial policy where they are clearly read only and low
  risk.
- Service managed StackSets require trusted access between Organizations and
  CloudFormation, which needs management account cooperation once.

## Alternatives rejected

**AWS managed `ReadOnlyAccess`.** Rejected. It permits S3 object reads, SSM
parameter reads and Secrets Manager metadata reads. None are needed, and the
posture cannot be defended in a security review.

**Per account manual role creation.** Rejected. It does not scale to 300
accounts and it silently breaks every time an account is vended.

**Identity propagated access for all reads.** Rejected for aggregate data.
Pre aggregated warehouse data cannot be fetched per user live. Identity
propagation is retained for live drill down only. See ADR-0008.
