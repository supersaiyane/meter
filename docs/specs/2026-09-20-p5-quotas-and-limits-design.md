# P5 Quotas and Limits: design specification

Date: 2026-09-20
Status: Provisional, pending approval
Sub project: P5
Features: FEAT-033, FEAT-034
Depends on: P0 delivered
Supersedes: nothing

## 1. Purpose

A quota is the only signal in this product that is not about money. It is about
the wall an estate hits at three in the morning, and the fact that somebody could
have seen it coming a fortnight earlier.

Two features, and the small one is the interesting one. FEAT-033 is quota
utilization. FEAT-034 is the workflow for doing something about it, and it is
interesting because the obvious implementation is a write API call into a member
account, which constraint 6 forbids.

## 2. Definition of done

- Every quota this product can measure shows used against limit, per service, per
  region.
- Every quota it **cannot** measure says so, by name, and never renders as zero
  used.
- A quota approaching its limit is a finding with a severity, ranked beside the
  rest.
- An increase request can be drafted, handed to a human, and then tracked to
  completion without Meter ever submitting it.

## 3. Out of scope

**Submitting a quota increase.** Decided 2026-09-20 and recorded here rather than
left implicit. See section 6.

**Quotas of anything but AWS.** The port is provider neutral; nothing reads GCP or
Azure.

**Predicting when a quota will be hit.** Trend against limit is arithmetic this
product could do, and a forecast is a different kind of claim governed by
ADR-0015's four conditions. It belongs with FEAT-048, not here.

## 4. Module structure

```
finops_core/
  domain/quota.py          QuotaUsage exists from P0 and is widened here. Its
                           existing rule already matters: unpublished usage is
                           None, never zero
  ports/quotas.py          QuotaSource exists from P0. Gains the increase
                           request history, which is a read
finops_providers/
  aws/quotas.py            Service Quotas for limits, AWS/Usage for the usage it
                           publishes, Trusted Advisor where the support tier
                           allows, service specific calls for the rest
  fake/quotas.py           An estate with quotas nobody can measure, on purpose
finops_ingest/collectors/
  quotas.py                One row per quota per region, every run, including
                           the ones with no usage source
finops_query/
  quota.py                 Headroom, and the severity rule. No provider
```

## 5. Data model

### 5.1 `quota_usage`

| Column | Why |
| --- | --- |
| `tenant_id`, `sub_account_id`, `region_id` | Scope, and the grain a quota lives at |
| `service_code`, `quota_code` | AWS's own identifiers, so a re read updates |
| `quota_name` | What a person calls it |
| `limit_value` | From Service Quotas. Nullable, because some quotas publish none |
| `used_value` | **Nullable, and the null is the point.** See 5.2 |
| `usage_source` | `AWS_USAGE_METRIC`, `TRUSTED_ADVISOR`, `SERVICE_API` or `NONE` |
| `is_adjustable` | Whether an increase can be requested at all |
| `as_of`, `collected_at` | Constraint 10 |

Unique on `(tenant_id, sub_account_id, region_id, service_code, quota_code)`.

Constraints, per constraint 11: `used_value <= limit_value` where both are
present, `usage_source = 'NONE'` if and only if `used_value IS NULL`, and
`limit_value >= 0`.

The second is the one worth reading twice. It makes it impossible to record a
usage figure without naming where it came from, and impossible to name a source
while recording no usage.

### 5.2 The rule this sub project exists to get right

**A quota with no usage source reports "limit known, usage unknown". It never
reports zero.**

FEAT-033 states the honest constraint plainly: there is no single API for used
against limit across all services. Service Quotas gives limits. The `AWS/Usage`
CloudWatch namespace gives usage for a subset. Trusted Advisor covers more and
needs Business or Enterprise support, which is OPEN-03. The remainder needs
service specific calls that do not all exist.

So most quotas in a real estate will have a limit and no usage, and a product that
renders that as "0 percent used" is telling somebody they have headroom nobody has
measured. That is constraint 5 with an outage behind it rather than a wrong number.

`used_value` is nullable, the database refuses a usage without a source, the screen
renders the null as a sentence, and the coverage figure at the top of the screen
says how many quotas could be measured out of how many exist.

### 5.3 `quota_request`

Read only. Meter never creates one; it reads the history AWS already keeps.

| Column | Why |
| --- | --- |
| `request_id` | AWS's, from `ListRequestedServiceQuotaChangeHistory` |
| `service_code`, `quota_code`, `region_id` | What was asked for |
| `desired_value` | How much |
| `status` | AWS's own: `PENDING`, `CASE_OPENED`, `APPROVED`, `DENIED`, `CASE_CLOSED` |
| `requested_at`, `last_updated_at` | AWS's timestamps |
| `as_of`, `collected_at` | Ours, constraint 10 |

## 6. Why Meter does not submit the request

`RequestServiceQuotaIncrease` is a write API call into a member account, and
constraint 6 says there are none in v1. Decided 2026-09-20: **track only.**

The reasoning is not squeamishness about this particular call, which is close to
harmless. It is that the read only property is worth more than any single feature
it costs. A product that has never written into a customer account can say so in
one sentence, and every security review after that is shorter. The first exception
ends that, and the second is always easier to argue than the first.

What Meter does instead:

1. Drafts the request, with the service, the quota, the current limit, the
   observed usage and a suggested new value with its working.
2. Shows the exact console link and the exact CLI command, so the human step is
   copy and paste rather than research.
3. Reads `ListRequestedServiceQuotaChangeHistory` and tracks the request to
   completion, which is the part actually missing today. Nobody loses a quota
   increase because they could not find the button. They lose it because nobody
   checked whether it was ever approved.

The Quota Request Template for organization wide defaults is also a write and is
treated the same way: Meter renders the template it would set, and does not set it.

## 7. Flow

```
Service Quotas  ---> limits, every quota, always
AWS/Usage       ---> usage, for the subset that publishes it
Trusted Advisor ---> usage, where the support tier allows. OPEN-03
Service APIs    ---> usage, for the few that have one
                          |
                          v
                  quotas collector
          writes every quota, with usage_source = NONE
              where nothing could measure it
                          |
            +-------------+--------------+
            v                            v
      quota_usage                  quota_request
   (headroom, severity)      (read from AWS history, never written)
```

Cadence is a `collector_schedule` row, ADR-0012. Twelve hourly: a quota does not
move quickly, and Service Quotas is rate limited per account.

## 8. Interface

| Route | Answers |
| --- | --- |
| `GET /governance/quotas` | Every quota, least headroom first, with the unmeasurable ones listed and marked |
| `GET /governance/quotas/{service}/{quota}` | One, with its history and a drafted increase |
| `GET /governance/quotas/requests` | Outstanding increase requests and their status |

## 9. User interface

`/governance/quotas` already exists in the navigation, marked as arriving with
this sub project.

The screen's hardest problem is the same as its data model's. A list sorted by
headroom puts the most urgent first, and a quota with no usage has no headroom to
sort by. Those are not zero headroom and must not sort as though they were.

So the screen is two lists under two headings: what we can measure, sorted by
headroom, and what we cannot, sorted by name, with the reason each one is
unmeasurable. The second list is expected to be longer, and its length is the
honest summary of how much of this problem AWS lets anybody solve.

A drafted increase renders as a console link and a CLI command, with a sentence
saying Meter will not submit it and why.

## 10. Infrastructure

No new stack. The org reader role gains `servicequotas:List*`, `servicequotas:Get*`
and `cloudwatch:GetMetricData` for the `AWS/Usage` namespace, all read only.

It notably does **not** gain `servicequotas:RequestServiceQuotaIncrease`, and that
absence is the enforcement of section 6. The permission is not there to be misused
later.

## 11. Testing

**The fake estate contains quotas nobody can measure.** Not one, several, in the
proportion a real estate has them, because a fake where every quota has usage makes
the null path the one nobody exercises, and section 5.2 is the whole sub project.

**A test asserts that no code path writes a quota.** The read only contract test
already covers member account writes generally; this one names the API, so a future
contributor adding the call fails a test whose name explains the decision.

## 12. Risks

**The unmeasurable list is so long the screen looks broken.** Likely, and the
mitigation is wording rather than hiding: the screen says how many quotas AWS
publishes usage for, and that the rest is a limitation of the provider rather than
of this product.

**OPEN-03.** Without Business or Enterprise support, Trusted Advisor contributes
nothing and the measurable list shrinks further. The adapter handles its absence as
`NotOptedIn`, which renders as a named gap rather than as missing quotas.

**Somebody adds the write later without reading this.** Mitigated by the IAM
permission being absent, by the test in section 11, and by this section existing.

## 13. Open questions

| ID | Question | Effect if unanswered |
| --- | --- | --- |
| OPEN-03 | Is Business or Enterprise support available | The measurable quota list is smaller. Everything else works |
| OPEN-06 | Regions | Answered 2026-08-23: eu-west-1 and eu-west-2 |

## 14. Features delivered

FEAT-033, and FEAT-034 in its track only form. Its feature document is updated to
say so, rather than leaving a reader to discover that the workflow submits nothing.

## 15. Exit criteria

1. Every quota in the seeded estate has a row, including the ones with no usage
   source.
2. A quota with no usage renders as unknown, never as zero, asserted by a test that
   checks the rendered text rather than the value.
3. The database refuses a usage figure with no source, asserted by an insert that
   tries.
4. A drafted increase shows a console link and a CLI command and submits nothing.
5. A request made outside Meter appears in the tracking list within one collection
   cycle.
6. No code path calls `RequestServiceQuotaIncrease`, asserted by name.
7. The IAM policy does not grant it.

None of these has been met against a real estate. ISS-122.
