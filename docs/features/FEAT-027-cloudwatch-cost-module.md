# FEAT-027: CloudWatch cost module

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Specified |
| Specification | [P3 spec](../specs/2026-09-20-p3-utilization-and-rightsizing-design.md), section 5.2 |
| Tasks | TASK-P3-009 |
| Refresh cadence | 24 hours |

## What it does

Finds the cheap wins in CloudWatch itself: log groups with no retention policy, high ingest groups with no queries in 90 days, duplicate delivery to both CloudWatch Logs and S3, custom metrics never queried, alarms stuck in insufficient data for 90 days.

## Why it exists

These findings are trivially detectable and typically pay for the whole platform in the first month.

## What is already known

Remediation levers are retention policies, the CloudWatch Logs Infrequent Access class, and export of cold logs to S3.

## How it works

The cheap wins in the service that bills for watching: log groups with no retention
policy, high ingest groups unqueried in 90 days, duplicate delivery to both
CloudWatch Logs and S3, custom metrics never queried, alarms stuck in insufficient
data.

"Unqueried in 90 days" is read from P2's existing evidence tables rather than
re collected. P2 asks what the queries cost; this asks what the storage and the
metrics cost. Different questions, different APIs, one shared piece of evidence.

Remediation names the lever: a retention policy, the CloudWatch Logs Infrequent
Access class, or export of cold logs to S3.

## Failure behaviour

An alarm in insufficient data for an hour is not a finding; one in that state for
30 days is. The threshold exists because the transient case is normal and flagging
it would teach a reader to skim the screen.

A log group Meter cannot read is reported as unreadable, not as having no
retention policy.

## Security considerations

Read only. `logs:Describe*` and `cloudwatch:Describe*` on the org reader role.

## Interface

`GET /waste/recommendations`, with the CloudWatch waste classes.

## Not doing

**Setting a retention policy.** Constraint 6, and this is the feature where it is
most tempting, because the fix is one API call and obviously correct. That is what
makes the first exception easy to argue.
