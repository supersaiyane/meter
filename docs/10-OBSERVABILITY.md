# Observability

Last updated: 2026-08-23
Update trigger: any new collector, any new SLO, any alert added or removed
Closes: AUDIT-001 finding A001-F14, ISS-066

Meter measures its own cost, FEAT-008. It did not measure its own health, which
is a different and more dangerous gap.

## The failure this exists to catch

**A FinOps platform that stops collecting is worse than one that is down.**

A platform that is down is obvious. Someone opens it, sees an error, and
raises a ticket. A platform that has silently stopped collecting for eleven of
three hundred accounts keeps serving pages that look right, keeps rendering
totals, and keeps being believed. Every figure is wrong by the cost of eleven
accounts, and nothing about the interface suggests it.

The design already has the ingredients: typed errors, `sync_error`, per
collector watermarks, and a freshness screen. What was missing is that all of
them surface **to a user who happens to look**. Nothing pages anyone.

## Service level objectives

Four. Deliberately few, because an SLO nobody can recite is not operated.

| # | SLO | Target | Measured by |
| --- | --- | --- | --- |
| 1 | **Collection freshness** | 99 percent of enabled collector and scope pairs are within 2 times their configured cadence, over 7 days | `ingest_watermark.as_of` against `collector_schedule.cadence_seconds` |
| 2 | **Collection success** | 99.5 percent of `ingest_run` rows reach `SUCCEEDED` or `PARTIAL`, over 7 days | `ingest_run.status` |
| 3 | **API latency** | p95 under 500 ms on scoped reads over pre aggregated rollups, over 7 days | Application Load Balancer target response time |
| 4 | **API availability** | 99.5 percent of requests return a non 5xx, over 30 days | Load balancer 5xx rate |

SLO 1 is the one that matters. The other three are ordinary service health, and
plenty of tools would catch them. SLO 1 catches the failure that is specific to
this product.

Note what SLO 2 counts as success: `PARTIAL` **is** success at the run level. A
run that completed while one account returned `AccessDenied` did its job. The
account level failure is SLO 1's problem, through the watermark that did not
advance. Conflating the two would make the run alert fire constantly at 300
accounts and it would be muted within a week.

## Alerts

An alert that does not lead to an action is deleted. Each row names the action.

| Alert | Condition | Severity | Action |
| --- | --- | --- | --- |
| **Collection stalled** | Any collector and scope pair with no watermark advance for 3 times its cadence | **Page** | Check `sync_error` for the typed cause. `AccessDenied` means the member role broke, `Throttled` means back off, `SchemaDrift` means AWS changed a payload |
| **Collection stalled, widespread** | More than 5 percent of scopes stalled at once | **Page** | Almost always the hub role, a credential, or an organization wide change. Do not chase individual accounts |
| Run failure rate | `FAILED` above 1 percent over 1 hour | Ticket | Read the typed errors. A single cause usually explains all of them |
| Dead letter queue not empty | Any message | Ticket | A unit failed 3 times. Inspect before purging, it is the only record |
| Retention job did not run | Any retention job absent for 48 hours | Ticket | Data is being kept past policy. See `docs/09-DATA-CLASSIFICATION.md` |
| API 5xx | Above 1 percent over 5 minutes | **Page** | Standard |
| API latency | p95 above 1.5 s over 15 minutes | Ticket | The ADR-0003 trigger to reconsider the serving layer. Capture the query plan before it resolves itself |
| Database connections | Above 80 percent of maximum | Ticket | Usually a leaked session in a collector |
| **Platform cost anomaly** | Meter's own daily cost above 2 times its 30 day median | **Page** | Meter is doing to itself what it exists to prevent. Check Athena scanned bytes and `GetMetricData` volume first |
| Security posture regressed | Nightly scan finds anything | Ticket | See `docs/05-SECURITY.md` |

Two of these are unusual and both are deliberate. **Collection stalled pages**,
because silent staleness is the failure mode of this product. **Platform cost
anomaly pages**, because a FinOps tool that quietly becomes expensive has no
standing left to comment on anyone else's bill.

## Telemetry

| Signal | Where | Retention |
| --- | --- | --- |
| Structured logs, JSON | CloudWatch Logs, `/ecs/meter-*` | 30 days, then Infrequent Access, then expire at 90 |
| Metrics | CloudWatch, namespace `Meter`, embedded metric format from the workers | 15 months, the CloudWatch default |
| Traces | AWS X-Ray, sampled at 5 percent, 100 percent on error | 30 days |
| Ingestion state | `ingest_run`, `ingest_watermark`, `sync_error` in PostgreSQL | 90 days |

**Every log line carries `run_id`, `collector`, `scope_key` and `tenant_id`.**
Without `scope_key` a log for one account is indistinguishable from a log for
another, and at 300 accounts that makes the logs useless exactly when they are
needed.

**No log line ever carries a credential, an ExternalId, or a value from a
member account.** Log the metadata and the typed error, never the payload.

### Meter's own log retention is a cost lever

Meter finds log groups with no retention policy and reports them as waste,
FEAT-027. Meter's own log groups therefore have retention set at creation, in
Terraform, not later. Failing to do so would be found by the product, in the
product, which is embarrassing in a specific and avoidable way.

## Dashboards

Three, in Amazon Managed Grafana, provisioned as code.

| Dashboard | Answers |
| --- | --- |
| **Collection health** | Is every collector current, per collector and per account. The internal twin of the user facing freshness screen |
| **Service health** | Latency, error rate, saturation, queue depth |
| **Platform cost** | Meter's own spend by module, against the estimate in `docs/04-DEPLOYMENT.md` |

These dashboards are subject to the project's own rules, which is a point worth
making explicitly. **Minimum refresh interval 1 minute, no Logs Insights panel
over a window longer than 24 hours.** FEAT-014 applies to us first. A team that
exempts its own dashboards from the control it sells has already lost the
argument.

## On call

| | |
| --- | --- |
| Hours | Business hours during P0 to P3. Reassess before any external dependency exists |
| Paging | Two alerts page: collection stalled, and platform cost anomaly. Everything else raises a ticket |
| Runbook | One per paging alert, in `docs/runbooks/`, written **with** the alert, never after |

An alert shipped without a runbook is a page that wakes someone who then has to
work out what to do. The runbook is part of the alert, not a follow up task.

## What is deliberately not built

| Not doing | Why |
| --- | --- |
| A separate observability stack | CloudWatch and Managed Grafana are already in the account and already understood. ADR-0013 rung four |
| Custom metrics for every collector | Four SLOs and the alerts above. Metrics nobody reads cost money per metric per month, which the product would flag |
| Real user monitoring | Tens of internal users. The load balancer is enough |
| Distributed tracing at 100 percent | 5 percent sampled, 100 percent on error. Full tracing is the same waste pattern this product exists to find |
