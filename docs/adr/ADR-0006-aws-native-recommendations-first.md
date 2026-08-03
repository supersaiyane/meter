# ADR-0006: Ingest AWS native recommendation services before building a collector

Date: 2026-08-23
Status: Accepted

## Context

The requirement asks Meter to scan resources, collect metrics, determine over
and under utilization, and propose a correct size with a saving. Building that
from raw CloudWatch metrics across every service is months of work.

AWS already provides Cost Optimization Hub, which is free, organization wide,
and consolidates rightsizing, idle resource, Graviton migration and commitment
purchase recommendations with estimated savings. Compute Optimizer provides
instance level analysis with an S3 export. Trusted Advisor adds more.

## Decision

Ingest Cost Optimization Hub, Compute Optimizer and Trusted Advisor first.
Build a bespoke collector only where AWS is blind.

Known blind spots that justify a bespoke collector: memory utilization, which
requires the CloudWatch agent, EBS provisioned versus used IOPS and
throughput, gp2 to gp3 migration, unattached volumes, aged snapshots, idle NAT
Gateways, idle load balancers, unassociated Elastic IPs, and DynamoDB
provisioned versus consumed capacity.

## Consequences

Positive.

- Weeks to a first useful recommendation set instead of months.
- AWS owns the accuracy of its own sizing model, which is easier to defend to
  an engineering team than a bespoke model.
- Meter's value moves to where it is actually differentiated: attribution,
  evidence, ownership, workflow, and realized savings verification.

Negative.

- A dependency on AWS service availability, regional coverage and format
  stability.
- Compute Optimizer requires opt in per organization, and Trusted Advisor
  limit checks require Business or Enterprise support. Both are stated as
  prerequisites rather than discovered at runtime.

## Alternatives rejected

**Build everything from raw CloudWatch metrics first.** Rejected. It
duplicates work AWS gives away, delays first value by months, and produces a
sizing model that is harder to defend.

## Binding rules for any bespoke recommendation

- Never recommend on fewer than 14 days of data.
- Use p95 and p99, never max.
- Batch `GetMetricData` at 500 metrics per call at one hour period. Never
  `GetMetricStatistics` per metric, which is both slow and separately billed.
- Account for burstable instance credits on T family instances.
- Recommend at Auto Scaling group level, not per instance.
- Every recommendation carries its evidence window, the statistic used, its
  confidence, and a measured or modelled flag.
