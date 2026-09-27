# FEAT-026: Bespoke waste collectors

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Delivered |
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

The screen draws modelled saving per waste class as a ranked bar above the queue, added
2026-09-27. The queue sorted by saving answers which single finding is largest. The chart answers
which kind of waste the estate has, which is the question that changes what somebody builds next.

Open findings only. A finding that is DONE has had its saving taken and one that is DISMISSED was
judged not to be waste, so charting the whole queue would draw money that is not available and
would grow the picture every time somebody fixed something.

Hatched, because every figure in it is modelled. The hatch is the same mark a figure and a bar
chart already use, so a reader learns it once. `provenance` is a required property on the
component rather than one that defaults to measured, because a default there is a default that
quietly promotes a modelled saving.

## Not doing

**Applying anything.** Constraint 6. Remediation is delivered as a generated
infrastructure as code pull request.
