# P14 Commitments: design specification

Date: 2026-10-13
Status: Approved by the owner on 2026-10-13 with OPEN-35 to OPEN-39 answered, in build. Chosen the same day as the next priority, proposal 5 of `next-in-scope.txt`
Sub project: P14
Features: FEAT-086, FEAT-087, FEAT-088, FEAT-089, FEAT-090
Depends on: P1 for commitment use and coverage, P9 for Savings Plans rates, P10 for FOCUS List Cost, P12 for the composition every new collector joins. Proof against a real estate waits on ISS-002, an AWS account
Supersedes: nothing. ADR-0037 amends ADR-0035's network rule

## 1. Purpose

Commitments are usually the largest saving a FinOps practice controls, and Meter can say how
much of each commitment was used and how much of the estate was covered, FEAT-024, and turn an
uncovered baseline into a finding, FEAT-055. It cannot say what the organization holds, when any
of it ends, how much the discounts actually saved, or what to buy next. A commitment's term is
inferred from the reporting window; the saving is a configured percentage, not a rate; and a
gap becomes a finding with no plan behind it.

P14 makes commitments manageable without making Meter a buyer. It reads every commitment the
organization holds with its real term, end date and payment; puts the effective savings rate,
measured from the bill, at the top of the screen; shows what expires in each coming month against
a ladder that keeps any one month small; and drafts a purchase plan from the estate's own usage and
P9's rates, beside AWS's own recommendation, for a person to approve, buy and see verified against
the bill. Constraint 6 holds throughout: Meter never calls a purchase API.

## 2. Definition of done

- Every Savings Plan and every reservation the organization holds, for EC2, RDS, ElastiCache,
  OpenSearch, Redshift and MemoryDB, lands with its real start, end, term, payment option and
  hourly commitment or quantity; an account that refuses reads as its typed cause.
- The commitments screen opens on the effective savings rate, measured from the bill's List Cost,
  by month, with the money behind it, and says why where the bill carries no List Cost.
- A renewal calendar shows what expires in each of the next twelve months and flags a month whose
  share passes the tenant's ladder limit.
- Meter drafts a purchase plan from the estate's own steady baseline and P9's Savings Plans rates
  under the tenant's policy, and shows it beside AWS's purchase recommendation with the difference
  explained. Every figure in a plan is modelled and says so.
- A plan moves from draft to approved to bought, each step recorded with who and when; once bought,
  Meter finds the commitment in the inventory and measures what it saved from the bill.
- The Cost Explorer reads made today run as the payer, which no role permitted, ISS-294.

## 3. Out of scope

- Buying, exchanging, selling or queueing a commitment. Constraint 6.
- DynamoDB reserved capacity: no API reads it, ISS-295. Its discount still shows in the bill.
- Commitments in Azure or GCP, which wait for proposal 8.
- Autonomous purchasing. The proposal says to partner rather than build it.

## 4. The gap, measured on 2026-10-13

| What | Today | Measured or modelled |
| --- | --- | --- |
| Commitment terms and end dates | Inferred from the reporting window, FEAT-024 "Not doing" | Measured, from the source |
| A commitment saving | `commitment_discount_percent`, a flat 30 percent setting | Measured, from the source |
| Roles granted the Cost Explorer commitment reports | 0; the collector calls as the hub, ISS-294 | Measured, from the Terraform |
| Reservable services with a read API | 7 of 8; DynamoDB reserved capacity has none | Measured, from botocore's service models |
| Interface endpoints the five relayed reads would need | 10, two collection Regions; about USD 160.60 a month | Modelled, at ADR-0035's USD 16.06 per endpoint |

## 5. Decisions

### 5.1 Purchase plans come from Meter and from AWS, side by side, OPEN-35

Meter drafts its own plan, section 5.6, and reads AWS's purchase recommendations from Cost
Explorer, `GetSavingsPlansPurchaseRecommendation` and `GetReservationPurchaseRecommendation`, for
the term and payment option the tenant's policy names. The screen shows both and explains the
difference in words: the lookback each used, the coverage each aims for, and the ladder only
Meter's applies. Each recommendation request costs USD 0.01 at AWS's published price, modelled;
eight a day, two Savings Plans types and six reservable services, is about USD 2.40 a month,
modelled, carried in the collector's schedule row. Answered by the owner on 2026-10-13: both.

### 5.2 Approval is recorded, and a person buys, OPEN-36

A plan is `DRAFT`, `APPROVED`, `BOUGHT`, `VERIFIED`, `WITHDRAWN` or `LAPSED`. Approving and
recording a purchase are writes to Meter's own database, each an event with the principal and the
time, made through the API by a principal whose scope is global, because a commitment belongs to the
payer, ADR-0025. A person buys in AWS. Once a plan is `BOUGHT`, the plan collector looks for a
commitment matching each line, by program, term, payment option and hourly commitment within one
percent, starting after the approval; a match is linked, and the plan becomes `VERIFIED` when every
line has one. A draft nobody approves within its month lapses, so a plan is never approved against
usage a month old. Answered by the owner on 2026-10-13: record it, a person buys.

### 5.3 The inventory covers every reservable service, OPEN-37

Savings Plans, `savingsplans:DescribeSavingsPlans`; and reservations for EC2,
`ec2:DescribeReservedInstances`; RDS, `rds:DescribeReservedDBInstances`; ElastiCache,
`elasticache:DescribeReservedCacheNodes`; OpenSearch, `es:DescribeReservedInstances`; Redshift,
`redshift:DescribeReservedNodes`; and MemoryDB, `memorydb:DescribeReservedNodes`. Each is read in
every member account, through its collector role, because a commitment is owned by the account that
bought it, and in every collection Region for the reservations. Savings Plans, EC2 and RDS are built
first and the other four follow. DynamoDB reserved capacity has no read API in botocore's service
model, measured on 2026-10-13, so it is recorded as unreadable, ISS-295, and its discount is seen
only in the bill's commitment columns. Answered by the owner on 2026-10-13: every reservable
service, Savings Plans, EC2 and RDS first.

### 5.4 A cautious ladder by default, per tenant, OPEN-38

The policy is data, as cadence is, constraint 9: `commitment_policy` holds a tenant's target
coverage of the steady baseline, its term, its payment option and its ladder limit, the largest
share of hourly commitment allowed to expire in any one month, with who changed it and why. The
default is 80 percent coverage, one year, no upfront, and one twelfth. Answered by the owner on
2026-10-13: the cautious ladder.

### 5.5 Reads made once a day go through the relay, OPEN-39, ADR-0037

Savings Plans have no interface endpoint, so their read joins the relay as ADR-0035 already
requires. RDS, ElastiCache, OpenSearch, Redshift and MemoryDB have endpoints, and ADR-0035's rule
would add one for each in both collection Regions, about USD 160.60 a month, modelled, for reads
made once a day. ADR-0037 amends the rule: a read made once a day or less, read only and allow
listed, may go through the relay even where an endpoint exists; the relay costs about a cent a month
for them, modelled. EC2 reservations use the EC2 endpoint the hub already pays for. Answered by the
owner on 2026-10-13: the relay, amending the rule.

### 5.6 Meter's plan: the steady baseline, P9's rates and the ladder

The plan is pure arithmetic in `finops_query`, so it can be tested without a database and every
figure in it can be traced:

1. **The baseline.** For each Savings Plans program, the daily on demand spend the bill shows on
   eligible usage that no commitment covered, over the last 30 days. The steady baseline is the
   tenth percentile of those days, divided by 24, so a quiet weekend sets it rather than a busy
   Monday. A day the bill does not hold is not a day of zero.
2. **The rate.** The discount is P9's Savings Plans rate against P9's on demand rate for the
   instance families and Regions that made up the baseline, weighted by their spend, for the
   policy's term and payment option. Where P9 holds no rate for a family, the plan says so for that
   share and does not price it.
3. **The target.** The policy's coverage of the baseline, less what active commitments already
   cover and what the inventory says they will still cover when the purchase would start.
4. **The ladder.** At most the ladder limit of the organization's hourly commitment may end in any
   one month. A plan buys this month's tranche, sized so the month it expires in stays within the
   limit given what already expires then, and names the months after it as later tranches.
5. **The figures.** Hourly commitment, modelled monthly saving and the usage floor, FEAT-055's
   honest figure, below which the commitment costs more than it saves: all modelled, each with
   the inputs it came from.

### 5.7 The effective savings rate is measured from the bill

One minus Effective Cost over List Cost, by month, on every line that carries a List Cost, the
KPI library's definition the overview tile already uses. The screen shows the rate, both sums and
the number of lines without a List Cost. A month whose lines carry none says so and shows no rate,
never a rate of zero. Measured.

### 5.8 The existing Cost Explorer reads run as the payer, ISS-294

`CostExplorerCommitmentReport` calls Cost Explorer with the hub's own credentials, and no Terraform
grants the hub `ce:GetSavingsPlansUtilization` or its neighbours; even if one did, Cost Explorer
answers for the organization only in the management account. P14's first task makes every
commitment read in Cost Explorer, the existing four and the two recommendation reads, as the
organization reader role in the management account, which gains exactly those actions, through the
Cost Explorer endpoint the hub already has in us-east-1.

## 6. Data model

New tables, each with `as_of` and `collected_at`, constraint 10, and each `PayerWide`, ADR-0025,
because a commitment belongs to the payer and its use cannot be apportioned:

- `commitment_inventory`: one commitment, keyed by tenant, kind and the source's identifier. Kind
  is `savings_plan` or `reservation`; program is the Savings Plans type or the reserved service;
  the owning account, the Region where it has one, the instance family or type, the quantity or the
  hourly commitment, term in months, payment option, upfront and recurring amounts, start, end and
  state. Checks hold a positive term, an end after a start, and exactly one of quantity or hourly
  commitment.
- `commitment_policy`: one row per tenant, target coverage between 0 and 1, term of one or three
  years, a payment option, a ladder limit between 0 and 1, who changed it, when and why. Installed
  for a new tenant and, by migration, for every existing one.
- `purchase_recommendation`: one of AWS's recommendations as AWS gave it, with its lookback, term,
  payment option, hourly commitment and estimated saving, which is AWS's and labelled so.
- `purchase_plan`, `purchase_plan_line` and `purchase_plan_event`: a plan with its status and the
  policy it was drafted under, a line per program, Region and tranche with its modelled figures and
  the commitment it was matched to, and an event per transition with the principal, the time and a
  note. A check holds the status to the six names, and a transition the API refuses cannot be
  written by any other path, constraint 11.

The bill gains nothing: FOCUS 1.4's `CommitmentDiscountId` and its status and type are already
stored, and `ListCost` is mapped.

## 7. Collectors and cadence

| Collector | Unit | Cadence | Reads |
| --- | --- | --- | --- |
| `commitment` | organization | daily | Cost Explorer use and coverage, as the payer from TASK-P14-001 |
| `commitment_inventory` | account and Region | daily | each service's describe call, section 5.3 |
| `purchase_recommendation` | organization | daily | Cost Explorer's two recommendation reads, as the payer |
| `purchase_plan` | organization | daily | Meter's own tables: drafts a plan, lapses an old draft, matches a bought plan to the inventory and measures it |

Each joins the registry, both compositions, the fakes, and a migration installing its cadence for
existing tenants.

## 8. Interface

- `GET /v1/commitments/inventory`: every commitment with its term and end, soonest ending first.
- `GET /v1/commitments/calendar`: the next twelve months, what expires in each and its share, and
  whether the share passes the ladder limit.
- `GET /v1/commitments/savings-rate`: the effective savings rate by month with both sums.
- `GET /v1/commitments/plans`: Meter's current plan and AWS's recommendations, side by side.
- `POST /v1/commitments/plans/{id}/approve`, `/bought` and `/withdraw`: a transition, with a note.
- `GET` and `PUT /v1/commitments/policy`: the tenant's policy, a change requiring a reason.
- The commitments screen opens on the savings rate and gains the inventory, the calendar and the
  plans, the last with the actions a principal may take.

Every response carries `as_of` and `collected_at`, constraint 10. The MCP facade gains the read
routes only, ADR-0009.

## 9. Testing

Each adapter is tested against recorded response shapes under moto where moto covers the call and
a stub where it does not, for every typed failure. The relay's allow list and the roles' policies are
read by tests that fail on a call or an action not listed. The plan's arithmetic is tested without a
database: a quiet weekend sets the baseline, a family with no P9 rate is unpriced rather than priced
at zero, and the ladder holds the limit given what already expires. The transitions are tested
through the API, including a narrowed principal refused and a transition out of order refused by the
database. The screen has unit tests and a Playwright journey on the seeded demo.

## 10. Risks

- Every adapter is checkable only against a real account, ISS-002.
- The plan models a saving from the bill's past and P9's rates. Usage that falls makes any plan
  wrong, which is why the usage floor is on every line and why a person approves.
- AWS's recommendation and Meter's will differ. The screen says why, rather than choosing one.
- A commitment bought in an account outside the organization never appears, and a plan line
  matched to nothing stays `BOUGHT`, which the screen shows as not yet seen, never as verified.

## 11. Open questions

OPEN-35 to OPEN-39, all answered by the owner on 2026-10-13, sections 5.1 to 5.5.

## 12. Features delivered

- FEAT-086: The commitment inventory: every commitment's real term, end and payment.
- FEAT-087: The effective savings rate as the headline, measured from the bill.
- FEAT-088: The renewal calendar and the ladder.
- FEAT-089: Purchase plans, Meter's and AWS's side by side.
- FEAT-090: Plan approval, the purchase recorded and verified against the bill.

## 13. Exit criteria

1. The Cost Explorer commitment reads are made as the payer, and the Terraform grants them, held
   by a test of the Terraform.
2. Every Savings Plan and reservation in the fake estate lands with its real term and end, and an
   account that refuses reads as its typed cause.
3. The commitments screen opens on the effective savings rate, measured, and a month with no List
   Cost says so.
4. The calendar flags a month whose expiring share passes the ladder limit.
5. Meter's plan and AWS's recommendation show side by side, every figure labelled, and a family
   with no rate is unpriced, never zero.
6. A plan approved, recorded as bought and matched to a new commitment becomes verified, each step
   recorded with its principal; a narrowed principal cannot approve.
