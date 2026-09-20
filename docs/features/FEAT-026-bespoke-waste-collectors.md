# FEAT-026: Bespoke waste collectors

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Specified |
| Specification | [P3 spec](../specs/2026-09-20-p3-utilization-and-rightsizing-design.md), section 5.2 |
| Tasks | TASK-P3-006 to TASK-P3-008 |
| Refresh cadence | 24 hours, 14 to 30 day window |

## What it does

Covers what AWS is blind to: memory utilization, EBS provisioned versus used, gp2 to gp3, unattached volumes, aged snapshots, idle NAT Gateways, idle load balancers, unassociated Elastic IPs, DynamoDB provisioned versus consumed.

## Why it exists

ADR-0006 rung six. Only build where the native services genuinely do not reach.

## What is already known

Binding rules: never recommend on fewer than 14 days, use p95 and p99 never max, batch `GetMetricData` at 500 metrics per call at one hour period, account for burstable credits, and recommend at Auto Scaling group level not per instance.

## How it works

What AWS is blind to, from CloudWatch metrics: memory utilization, EBS provisioned
against used, gp2 to gp3, unattached volumes, aged snapshots, idle NAT Gateways,
idle load balancers, unassociated Elastic IPs, DynamoDB provisioned against
consumed.

The binding rules are in the specification rather than in somebody's judgement:
never recommend on fewer than 14 days, use p95 and p99 and never max, batch
`GetMetricData` at 500 metrics per call at a one hour period, account for burstable
credits, and recommend at Auto Scaling group level rather than per instance.

The batching rule is not premature optimisation. `GetMetricData` is charged per
metric requested, and a naive one call per instance implementation on a three
hundred account estate is a line item that would appear on our own platform cost
screen.

## Failure behaviour

**A metric window that returned nothing is not a resource with no usage.** An
absent key means unobserved, exactly as `query_evidence` already treats it. A
collector reading zero data points and concluding the instance was idle would
recommend terminating a running system, which is the most expensive possible
instance of rendering a failure as zero.

An instance at 20 percent with a healthy burstable credit balance is correctly
sized and produces nothing. The fake estate contains one, so a detector that flags
everything low fails.

## Security considerations

Read only. `cloudwatch:GetMetricData` and the describe calls for the resource types
above.

## Interface

`GET /waste/recommendations`, with a `source` of `METER`.

## Not doing

**Applying anything.** Constraint 6. Remediation is delivered as a generated
infrastructure as code pull request.
