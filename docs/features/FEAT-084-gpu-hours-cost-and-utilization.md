# FEAT-084: GPU hours, cost and utilization

| Field | Value |
| --- | --- |
| Sub project | P13 |
| Status | In build |
| Specification | [P13 spec](../specs/2026-10-12-p13-finops-for-ai-design.md), section 5.6 |
| Tasks | TASK-P13-006 and TASK-P13-007 |
| Decisions | OPEN-33 |
| Issues addressed | None yet |
| Refresh cadence | Daily, for the day before |

## What it does

Lists every GPU instance in the bill with its hours and cost, and beside each EC2 instance the
average and peak GPU utilization the CloudWatch agent published, or not published.

## Why it exists

A GPU instance is among the most expensive lines on a bill and the bill cannot say whether the GPU
did any work. Utilization is the number that says whether the spend bought anything.

## How it works

Built so far: the utilization, TASK-P13-006, and `GET /ai/gpu`, TASK-P13-007: each GPU instance the
bill names with its hours and cost, and published, partly published or not published.

Hours and cost are a query over `cost_focus_daily` for usage types naming a `p`, `g`, `trn`, `inf`
or `dl` instance type. The `gpu_utilization` collector reads `nvidia_smi_utilization_gpu` for each
EC2 GPU instance the bill names, in the namespace `gpu_metrics_namespace` names, and writes the
day's average and peak across the instance's GPUs to `gpu_utilization_daily`.

## Data sources and freshness

| Source | Cadence | Best possible freshness |
| --- | --- | --- |
| The AWS FOCUS export | The cost collector's | Several times a day |
| CloudWatch agent NVIDIA metrics | Daily | The day before |

`as_of` is the end of the day read; `collected_at` is when the collector read it.

## Measured or modelled

Hours, cost and utilization are measured.

## Failure behaviour

An instance that publishes no GPU metric has no utilization row and reads not published, never zero
percent. A read that fails is typed and the instance's hours and cost still show.

## Security considerations

Reads CloudWatch metrics with the permissions the collector role already holds,
`cloudwatch:ListMetrics` and `cloudwatch:GetMetricData`, under the scope of each instance's
account.

## Interface

`GET /v1/ai/gpu`, and the GPU panel of the AI spend screen.

## Not doing

SageMaker and EKS utilization, whose hours and cost show from the bill. Installing or configuring
the CloudWatch agent, which is a write.
