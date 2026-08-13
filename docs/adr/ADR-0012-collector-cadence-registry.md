# ADR-0012: Collection cadence is data, not code, and is bounded by the source

Date: 2026-08-23
Status: Accepted

## Context

The question asked was how often cost and sizing data refreshes, with a stated
requirement that the Grafana query audit refresh every six hours.

Behind it sits a constraint that has to be stated plainly, because it limits
what any tool can promise.

## The constraint

**Cost data freshness is capped by AWS, not by Meter.**

| Source | How fresh it can possibly be |
| --- | --- |
| Cost and Usage Report, CUR 2.0 | Refreshed up to three times a day. Restated throughout the month |
| Cost Explorer | Roughly 24 hours behind |
| Compute Optimizer | Rebuilt daily at best, over a 14 day lookback |
| Cost Optimization Hub | Daily |
| CloudWatch metrics | 1 to 5 minutes |
| CloudTrail via EventBridge | Seconds to a few minutes |
| AWS Config | Change driven, near real time |

Polling CUR hourly produces the same numbers as polling it every eight hours,
and pays for the Athena scan each time. A tool that claims hourly cost
freshness is either wrong or is reporting the age of its own copy rather than
the age of the data.

So Meter reports two distinct timestamps on every figure: `as_of`, when the
data was true at the source, and `collected_at`, when Meter fetched it.
Conflating them is how a stale number looks fresh.

## Decision

**Cadence lives in a `collector_schedule` table, not in code.** Each row
carries the collector, the cadence, the reason, the estimated cost per run, and
who last changed it. The dispatcher reads the table. Changing a cadence is a
configuration change with a visible cost, not a code deploy.

Defaults:

| Collector | Cadence | Reason |
| --- | --- | --- |
| `org_tree` | 1 hour | P0 requires a new account to appear within an hour |
| `account_health` | 1 hour | A broken onboarding must be visible quickly |
| `platform_cost` | 24 hours | Cost Explorer charges per request |
| `cur_focus` | 4 hours | The source refreshes at most three times a day |
| `cur_focus_final` | daily, day 3 to 5 of the next month | The billing period is only final after restatement stops |
| `grafana_query_audit` | **6 hours** | Requested. The audit is a survey, not a control |
| `grafana_kill_switch` | **event driven** | CloudTrail `StartQuery` through EventBridge. Prevention cannot wait 6 hours |
| `compute_optimizer` | 24 hours | The source rebuilds daily |
| `cost_optimization_hub` | 24 hours | The source rebuilds daily |
| `metrics_rightsizing` | 24 hours, 14 to 30 day window | A p95 over 30 days does not move hourly |
| `config_inventory` | 6 hours, plus change driven | EventBridge covers changes between sweeps |
| `quotas` | 6 hours | Headroom is a risk signal, not a live one |
| `k8s_telemetry` | 15 minutes, pushed | An in cluster agent pushes, Meter does not poll |
| `cost_anomaly` | 6 hours | The source publishes a few times a day |

## The point about Grafana

Six hours is right for the **audit**, which surveys every dashboard and models
cost. It is wrong for the **control**.

A six hour survey of the failure that started this project would still have let
roughly 25,000 USD burn between sweeps. So the kill switch is event driven:
CloudTrail `StartQuery` through EventBridge, counted per principal per hour,
breaching into an alert and a Budgets Action.

Two mechanisms, two cadences, and the roadmap treats them as separate features,
FEAT-011 and FEAT-015.

## Consequences

Positive.

- Every figure carries the age of the data and the age of the copy, so a stale
  number cannot look fresh.
- Changing a cadence shows its cost before it is changed, which is the
  behaviour the product exists to encourage.
- Per tenant overrides are a row, not a branch.

Negative.

- A configurable cadence can be set to something expensive. Mitigated by
  showing the estimated monthly cost of a cadence change in the interface
  before it is saved, and by the change appearing in `platform_cost`.

## Alternatives rejected

**One global refresh interval.** Rejected. A CloudTrail derived control and a
monthly billing reconciliation have nothing in common, and a single interval
is either wasteful for one or useless for the other.

**Cadence as a constant in code.** Rejected. Changing how often data refreshes
should not require a deploy, and the reason for a cadence belongs next to the
cadence.
