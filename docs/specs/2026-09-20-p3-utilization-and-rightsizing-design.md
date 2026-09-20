# P3 Utilization and Rightsizing: design specification

Date: 2026-09-20
Status: Provisional, pending approval
Sub project: P3
Features: FEAT-025, FEAT-026, FEAT-027, FEAT-028, FEAT-029, FEAT-043, FEAT-044
Depends on: P0 delivered, P1 delivered
Supersedes: nothing

## 1. Purpose

P1 says what the estate costs. P3 says what it should cost instead, names who
will change it, and then checks whether the bill actually moved.

The third of those is the sub project. The first two are what every FinOps tool
does, and ISS-029 is the reason the third exists: identified savings is a vanity
metric that every tool inflates, because nothing in the tool is ever measured
against the invoice afterwards. FEAT-029 is the north star, and every other
feature here is upstream of it.

## 2. Definition of done

- A recommendation exists for every waste class in section 5, from AWS's own
  services and from our own collectors, in one table with one lifecycle.
- Every recommendation carries a **money** estimate, a **confidence** and an
  **owner**, and none of the three is optional.
- A recommendation marked done is checked against the bill 60 days later and is
  marked `verified` or `regressed` on the evidence.
- Estimated savings and realized savings are never added together, never shown in
  the same column, and never summed into one figure.
- No write API call reaches a member account. Constraint 6. Remediation is a
  generated infrastructure as code pull request.

## 3. Out of scope

**Automatic application of any change.** FEAT-044 scores blast radius so that a
future auto apply has a gate to consult, and v1 has no auto apply to gate. The
score informs a human. Building the gate before the thing it gates is deliberate:
the alternative is writing the write path first and adding safety afterwards.

**Savings plan and reservation purchase recommendations.** AWS produces them and
FEAT-024 already shows what is committed and covered. A purchase recommendation
presented beside our own figures would imply we had checked it against them, and
we have not. It joins P3 when somebody has.

**Anything needing a support tier we do not have.** Trusted Advisor limit checks
need Business or Enterprise support, which is OPEN-03 and unanswered. The adapter
is written to read them and its task says plainly that it has not.

## 4. Module structure

Nothing here breaks the layer contract. `finops_core` gains ports and entities and
imports no SDK.

```
finops_core/
  domain/waste.py          Recommendation, SavingsEstimate, RealizedSaving,
                           Confidence, Lifecycle. Money is Decimal
  ports/recommendations.py RecommendationSource, one method per provider service
  ports/tickets.py         TicketSink. OPEN-05 is unanswered, so this is a port
                           with a fake and no adapter
finops_query/
  waste.py                 The arithmetic. p95 and p99 over a series, the 14 day
                           refusal, and the saving estimate per waste class. No
                           database, no clock, no provider
  score.py                 The FinOps Score, and its decomposition
finops_providers/
  aws/recommendations.py   Cost Optimization Hub, Compute Optimizer, Trusted
                           Advisor. Unproved, ISS-122
  aws/waste.py             The bespoke collectors. GetMetricData batched
  fake/recommendations.py  An estate with waste in it, including waste that is
                           not waste
finops_ingest/collectors/
  recommendations.py       AWS native, upserted on the provider's own identifier
  waste_compute.py         Bespoke, from metrics
  waste_cloudwatch.py      FEAT-027, the module with no instances to size
  realized_savings.py      The 60 day check against the bill
```

## 5. Data model

Four tables. The shape that matters is that there is **one** recommendation
table, not one per source.

### 5.1 `recommendation`

One row per finding, whatever produced it. A lifecycle that works for a Compute
Optimizer recommendation and not for an unattached volume is two lifecycles, and
the second one is the one nobody maintains.

| Column | Why |
| --- | --- |
| `recommendation_id` | Ours |
| `tenant_id`, `sub_account_id` | Scoped by account, like every cost table |
| `source` | `COMPUTE_OPTIMIZER`, `COST_OPTIMIZATION_HUB`, `TRUSTED_ADVISOR`, `METER` |
| `source_reference` | The provider's own identifier, so a re read updates rather than duplicates |
| `waste_class` | From the enumeration in 5.2 |
| `resource_id`, `region_id` | What to change |
| `estimated_monthly_saving` | **Modelled**, always. `NUMERIC(20, 10)` |
| `confidence` | `HIGH`, `MEDIUM`, `LOW`. Never derived from the money |
| `severity` | Derived from the money, ADR-0016. Never entered by hand |
| `observation_days` | How many days the estimate rests on. Below 14 there is no row at all |
| `lifecycle` | `OPEN`, `ACCEPTED`, `IN_PROGRESS`, `DONE`, `VERIFIED`, `REGRESSED`, `DISMISSED` |
| `owner`, `ticket_reference` | Nullable, and a null owner is a reported condition |
| `rationale` | The working, as `cost_anomaly.why` carries it |
| `as_of`, `collected_at` | Constraint 10 |

**Confidence is not severity, and the two must never be collapsed.** Severity
answers how much money is at stake. Confidence answers how sure the estimate is. A
ten thousand dollar recommendation resting on three days of data is `CRITICAL` and
`LOW`, and a reader needs both numbers to decide whether to act this week. A single
blended score would hide exactly the recommendation most worth arguing about.

Database constraints, per constraint 11: `estimated_monthly_saving >= 0`,
`observation_days >= 14`, `severity` and `lifecycle` and `confidence` in their
enumerations, and a unique key on `(tenant_id, source, source_reference)`.

### 5.2 Waste classes

From FEAT-026 and FEAT-027, and the list is closed. A free text class is a class no
screen can label and no score can weight.

`RIGHTSIZE_INSTANCE`, `IDLE_INSTANCE`, `GRAVITON_CANDIDATE`, `EBS_OVERPROVISIONED`,
`EBS_GP2_TO_GP3`, `EBS_UNATTACHED`, `SNAPSHOT_AGED`, `NAT_GATEWAY_IDLE`,
`LOAD_BALANCER_IDLE`, `ELASTIC_IP_UNASSOCIATED`, `DYNAMODB_OVERPROVISIONED`,
`LOG_GROUP_NO_RETENTION`, `LOG_GROUP_UNQUERIED`, `LOG_DUPLICATE_DELIVERY`,
`METRIC_UNQUERIED`, `ALARM_INSUFFICIENT_DATA`.

### 5.3 `recommendation_event`

Append only. One row per lifecycle transition, with who and when.

The lifecycle column is not the lifecycle. It tells you where a recommendation is;
it cannot tell you that somebody accepted it in March, nothing happened, and it was
quietly dismissed in June. ISS-028 says recommendations without a workflow are
ignored every time, and an audit of the workflow is the only way to watch that
happening.

### 5.4 `realized_saving`

The measured half, in its own table so it cannot be summed with the estimate by
accident.

| Column | Why |
| --- | --- |
| `recommendation_id` | What was done |
| `window_before_start`, `window_before_end` | 30 days before `done_at` |
| `window_after_start`, `window_after_end` | 30 days ending 60 days after `done_at` |
| `cost_before`, `cost_after` | **Measured**, from `cost_focus_daily` |
| `usage_before`, `usage_after` | The control, see 5.5 |
| `realized_monthly_saving` | `cost_before` minus `cost_after`, adjusted |
| `verdict` | `VERIFIED`, `REGRESSED`, `INCONCLUSIVE` |
| `why` | The working |

### 5.5 What a realized saving can and cannot claim

This is the most important paragraph in the specification, because it is where a
FinOps tool usually starts lying.

A resource that cost 100 dollars before and 60 after did not necessarily save 40.
It may simply have been used less. The honest counterfactual, what that resource
would have cost had nothing changed, is unobservable, and any tool claiming to know
it is modelling and calling it measurement.

So P3 claims exactly this: **the amortized cost of the affected resource fell by
this much, and its usage quantity moved by this much over the same window.** Both
numbers are shown. Where usage fell by more than cost did, the verdict is
`INCONCLUSIVE` rather than `VERIFIED`, because the saving cannot be told apart from
a workload that shrank on its own.

`INCONCLUSIVE` is expected to be common. A north star metric that is only ever green
is the vanity metric ISS-029 warns about, and the inconclusive verdicts are the
evidence that this one is not.

## 6. Error taxonomy

The six causes from P0, unchanged. Two notes specific to here.

**`NotOptedIn` is an expected state, not an error condition.** Compute Optimizer
requires an organization level opt in, ISS-004 and OPEN-03. An estate without it
reports zero AWS native recommendations, which must render as "not opted in, here is
how" and never as "no waste found".

**A metric window that returned nothing is not a resource with no usage.** An absent
key means unobserved, exactly as `query_evidence` already treats it. A collector that
read zero data points and concluded the instance was idle would recommend terminating
a running system, which is the most expensive possible instance of rendering a
failure as zero.

## 7. Flow

```
                     +- Cost Optimization Hub -+
AWS native:          +- Compute Optimizer -----+--> recommendations collector
                     +- Trusted Advisor -------+         (source_reference key)
                                                                |
Bespoke:      CloudWatch GetMetricData --> finops_query.waste ---+
              (batched 500, 1h period)     p95/p99, 14 days min  |
                                                                 v
                                                         recommendation
                                                                 |
                                        +------------------------+
                                        v                        v
                              recommendation_event         FinOps Score
                              (owner, ticket)              (decomposed)
                                        |
                                   lifecycle = DONE
                                        |  + 60 days
                                        v
                              realized_savings collector
                              reads cost_focus_daily
                                        |
                                        v
                                 realized_saving
```

**Cadence is data, not code**, per ADR-0012. AWS native recommendations refresh
daily, bespoke collectors every six hours, realized savings daily, the score every
six hours. Each row in `collector_schedule` carries its reason and its cost, and
`GetMetricData` is charged per metric requested, which is why the batching rule is in
the specification rather than in somebody's judgement.

## 8. Interface

| Route | Answers |
| --- | --- |
| `GET /waste/recommendations` | Worst money first, filterable by class, lifecycle and owner |
| `GET /waste/recommendations/{id}` | One, with its events and its working |
| `POST /waste/recommendations/{id}/accept` | Lifecycle transition, writes an event |
| `POST /waste/recommendations/{id}/dismiss` | Same, and dismissal requires a reason |
| `GET /waste/savings` | Realized, never mixed with estimated |
| `GET /waste/score` | The score and its components |

Every transition route is a `POST` with no body, like the remediation routes already
in P2: what to write is decided by the server from the row it already holds.

## 9. User interface

Three screens, all currently marked unbuilt and named for this sub project.

`/waste` lists recommendations ranked by money. Two columns that must not be
adjacent: the estimated saving and the confidence. A reader comparing them side by
side reads confidence as a discount on the money, which it is not.

`/waste/savings` is the one screen in this product where a number is allowed to be
disappointing. It shows realized against estimated, and the gap is the point.
`INCONCLUSIVE` rows are listed, not hidden.

`/waste/score` shows the score and, immediately below it, the components that
produced it and the findings that moved each one since the last run. FEAT-043 ships
only if this decomposition exists, which is its own stated condition.

## 10. Infrastructure

No new stack. The collectors run on the existing worker. Compute Optimizer and Cost
Optimization Hub need an organization level opt in, which is a console or API action
in the payer account and is a prerequisite rather than Terraform.

The org reader role gains `compute-optimizer:Get*`, `cost-optimization-hub:List*`,
`support:Describe*` and `cloudwatch:GetMetricData`, all read only.

## 11. Testing

Same contract as P1. Every collector proved against a fake estate, every adapter held
to a contract suite parameterised over both providers, every route called through the
client rather than imported.

Three tests this sub project needs that P1 did not.

**An estate with waste that is not waste.** The fake must contain a burstable instance
running at 20 percent that is correctly sized because of its credit balance, and a
development instance idle at night that is not waste. A fake where everything low is
wasteful proves nothing about a detector.

**A recommendation whose saving did not persist.** The fake estate must produce a
`REGRESSED` verdict, or the verification path is never exercised in the direction
that matters.

**A graph the scorer cannot trust.** See section 12.

## 12. Risks

**The one that could cause harm: blast radius scored from an incomplete graph.**
FEAT-044 walks P4's edge tables. A region Meter could not read contributes no edges,
so a resource with forty dependents in that region scores as having none, and the
score says the change is safe. That is the partial failure rule with money and uptime
behind it.

The rule: **blast radius refuses to score when the graph is known incomplete for the
resource's account or region.** It returns no score and a reason, and the screen
renders the refusal. A missing score reads as "we do not know", which is the truth. A
low score would read as "safe", which would be a lie the product told on its own
initiative.

**The FinOps Score becomes a number nobody can argue with.** Mitigated by its own ship
condition, FEAT-043: it decomposes or it does not ship.

**`GetMetricData` cost.** Charged per metric requested. Mitigated by the 500 metric
batch at one hour period, written into the specification, and by the platform metering
itself so the cost of the P3 collectors appears on the front page like every other
module.

**Estimates that never meet a bill.** The whole point of FEAT-029, and the reason it
is not deferred to a second cut.

## 13. Open questions

| ID | Question | Effect if unanswered |
| --- | --- | --- |
| OPEN-03 | Is Business or Enterprise support available | Trusted Advisor limit checks are absent. Everything else in FEAT-025 works |
| OPEN-05 | Jira or ServiceNow | Answered for planning purposes on 2026-09-20 as **neither yet**. A `TicketSink` port with a fake is built, and the adapter is one task blocked on this question. The lifecycle is complete without it |

## 14. Features delivered

FEAT-025, FEAT-026, FEAT-027, FEAT-028, FEAT-029, FEAT-043, FEAT-044.

FEAT-044 is last and depends on P4, which the plan states rather than leaving for
somebody to discover.

## 15. Exit criteria

1. A recommendation exists for every waste class in 5.2, from a seeded estate.
2. A recommendation moves through its whole lifecycle, and the events record it.
3. A `VERIFIED`, a `REGRESSED` and an `INCONCLUSIVE` verdict all exist in a seeded
   estate, and the screen renders the third without apology.
4. Estimated and realized savings cannot be summed, asserted by a test that tries.
5. The score decomposes to findings, asserted by a test that changes one finding and
   checks the component that moves.
6. Blast radius refuses to score against an incomplete graph, asserted by a test that
   removes a region's edges and requires a refusal rather than a low score.
7. No write API call reaches a member account, asserted by the existing read only
   contract test.

None of these has been met against a real estate, and cannot be until ISS-122 is
resolved. They are met against the fake, and the plan says so rather than implying
otherwise.
