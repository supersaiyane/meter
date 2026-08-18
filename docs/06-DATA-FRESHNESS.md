# Data freshness and refresh cadence

Last updated: 2026-08-23
Update trigger: any cadence change, any new collector
Decision: ADR-0012

The question was how often cost and sizing data refreshes, with a requirement
that the Grafana audit refresh every six hours.

The honest answer starts with a constraint, because it limits what any tool in
this category can promise.

## Freshness is capped by AWS, not by Meter

| Source | Best possible freshness | Note |
| --- | --- | --- |
| Data Exports CUR 2.0 | Up to 3 times a day | Restated throughout the month |
| Cost Explorer | Roughly 24 hours behind | Charged per request |
| Compute Optimizer | Daily, over a 14 day lookback | Needs an organization opt in |
| Cost Optimization Hub | Daily | Free |
| Savings Plans and RI coverage | Daily | |
| Cost Anomaly Detection | A few times a day | |
| CloudWatch metrics | 1 to 5 minutes | Charged per metric requested |
| AWS Config | Change driven, near real time | Recording cost is significant |
| CloudTrail through EventBridge | Seconds to a few minutes | |
| Service Quotas and `AWS/Usage` | Minutes | Roughly 70 percent coverage |

Polling CUR hourly returns the same numbers as polling it every eight hours,
and pays for the Athena scan each time. A tool advertising hourly cost
freshness is either wrong, or is reporting the age of its own copy rather than
the age of the data.

## Two timestamps, always

Every figure in Meter carries both.

| Field | Meaning |
| --- | --- |
| `as_of` | When the data was true at the source |
| `collected_at` | When Meter fetched it |

Conflating these is how a stale number looks fresh. A CUR figure collected five
minutes ago can still be describing yesterday, and the interface says so.

## Cadence is configuration, not code

Cadence lives in a `collector_schedule` table. Each row carries the collector,
the cadence, the reason, the estimated cost per run, and who last changed it.
The dispatcher reads the table.

Changing a cadence is a configuration change with a visible cost, not a deploy.
The interface shows the estimated monthly cost of a change before it is saved,
which is the behaviour the product exists to encourage, applied to itself.

## Defaults

| Collector | Cadence | Reason |
| --- | --- | --- |
| `org_tree` | 1 hour | A new account must appear within an hour |
| `account_health` | 1 hour | Broken onboarding must be visible quickly |
| `platform_cost` | 24 hours | Cost Explorer charges per request |
| `cur_focus` | 4 hours | The source refreshes at most three times a day |
| `cur_focus_final` | Daily, days 3 to 5 of the next month | A billing period is only final once restatement stops |
| `cost_explorer_rollup` | 24 hours | Metered API, and the source is a day behind |
| **`grafana_query_audit`** | **6 hours** | Requested. This is a survey, not a control |
| **`grafana_kill_switch`** | **Event driven** | CloudTrail through EventBridge. Prevention cannot wait |
| `compute_optimizer` | 24 hours | The source rebuilds daily |
| `cost_optimization_hub` | 24 hours | The source rebuilds daily |
| `metrics_rightsizing` | 24 hours, 14 to 30 day window | A p95 over 30 days does not move hourly |
| `config_inventory` | 6 hours, plus change driven | EventBridge covers changes between sweeps |
| `quotas` | 6 hours | Headroom is a risk signal, not a live one |
| `cost_anomaly` | 6 hours | The source publishes a few times a day |
| `k8s_telemetry` | 15 minutes, pushed | An in cluster agent pushes, Meter does not poll |

## The Grafana six hour requirement, answered precisely

Six hours is right for the **audit**. It walks every workspace, dashboard,
panel and alert rule, models cost, and ranks the results. That is a survey, and
a survey does not need to be live.

Six hours is wrong for the **control**. The failure that started this project
burned roughly 100,000 USD in a week. At an even burn rate a six hour gap is
still around 25,000 USD between sweeps.

So the two are separate features at separate cadences.

| | Feature | Cadence | Answers |
| --- | --- | --- | --- |
| Audit | FEAT-011, FEAT-012, FEAT-013 | 6 hours | What is expensive, who owns it, what should change |
| Control | FEAT-014, FEAT-015 | On save, and event driven | Stop this from happening at all |

The workspace level minimum refresh interval, FEAT-014, is not a cadence at
all. It is a setting Grafana enforces on every save, it costs nothing, and it
removes most of the exposure on its own.

## Wanting fresher cost data than AWS provides

The reasonable answer is not to poll harder. It is to watch the drivers.

| Want | Do not | Do |
| --- | --- | --- |
| Know about a cost spike today | Poll CUR hourly | Watch the usage driver in CloudWatch, for example log group `IncomingBytes`, at 5 minute resolution |
| Know who started an expensive query | Wait for the bill | CloudTrail `StartQuery` through EventBridge, in seconds |
| Know a resource was created | Poll a describe loop | AWS Config change events |
| Know the month is trending over | Recompute from CUR constantly | Cost Anomaly Detection, plus the 4 hour CUR ingest |

Meter shows the driver signal as near real time and the money as of the last
CUR refresh, and labels each accordingly. A driver spike is an early warning,
not a cost figure, and presenting it as a cost figure would be the same
dishonesty as rendering a failure as a zero.

## Per tenant overrides

A row in `collector_schedule`, not a branch in code. A tenant that wants the
Grafana audit hourly can have it, sees the estimated cost before saving, and
sees the actual cost afterwards in `platform_cost`.
