# Runbook: commitments

The owner's steps to give Meter the organization's commitments, and to act on a purchase plan, each
with the check that says it worked. P14, FEAT-086 to FEAT-090, TASK-P14-010.

> **Nothing here has been done against a real account yet.** Every read is written to the service's
> published model and tested against recorded shapes, ISS-002, and Cost Explorer's names for four
> reserved services are unverified, ISS-297. Expect the first run of each step to find something,
> and record it in `tasks/ISSUES.md` as it happens.

**Meter never buys, constraint 6.** No role, the relay, or any production module may call a purchase
API, and `tests/contract/test_no_commitment_purchases.py` fails the build if one could. A person
buys in the AWS console; Meter records the decision and checks the purchase afterwards.

## Give Meter the reads

| # | Step | Check |
| --- | --- | --- |
| 1 | Apply `infra/terraform/management`, which grants the organization reader role Cost Explorer's five commitment reports and AWS's two purchase recommendations, as the payer | The plan shows the role's policy gaining seven `ce:` reads and no purchase action |
| 2 | Roll the member StackSet, so each account's collector role reads its Savings Plans and the six reserved services' describe calls | Every StackSet instance is current |
| 3 | First contact, below | Each line P14 adds reads `answered` |
| 4 | Where Cost Explorer refuses a service name, set `METER_COMMITMENT_RECOMMENDATION_SERVICES` to the names it accepts, ISS-297 | The next `purchase_recommendation` run writes that service with no cause |
| 5 | Wait a day for the daily runs | The commitments screen, under Optimize, shows what is held, when it ends, and a plan |

Step 3, with credentials for the hub account and `AWS_REGION` set to the hub's Region:

```bash
make first-contact ENV=dev ACCOUNT=<a member account id> REGION=<a Region it uses>
```

The lines P14 adds:

| Line | Collector | Reached as |
| --- | --- | --- |
| Cost Explorer's commitment reports, as the payer | `commitment` | The organization reader role |
| Cost Explorer's Savings Plans purchase recommendation, as the payer | `purchase_recommendation` | The organization reader role |
| Cost Explorer's reservation purchase recommendation, as the payer | `purchase_recommendation` | The organization reader role, for the first service the setting names |
| EC2 reservations the account holds | `commitment_inventory` | The member's collector role, through its endpoint |
| Savings Plans, RDS, ElastiCache, OpenSearch, Redshift and MemoryDB, through the relay | `commitment_inventory` | The member's collector role, through the relay, ADR-0037 |

A line reading `AccessDenied` as the payer means step 1 is not applied, or the role's ExternalId does
not match the hub's; through the relay, it means the StackSet in step 2 has not reached that account.

## The purchase policy

Each tenant starts on the cautious ladder, OPEN-38: 80 percent of the steady baseline, a year's term,
no upfront, and at most a twelfth of the commitment ending in any month. A person whose scope is the
whole organization changes it, with a reason, through `PUT /v1/commitments/policy`; the change is
audited and the next day's plan is drafted under it. The screen does not edit the policy yet.

## Acting on a plan

Meter drafts a plan for each month, daily, and redrafts it while nobody has approved it. What a
person approves and buys is the plan's own month's tranche; the later tranches are named so the
ladder can be seen, and are drafted again in their own months. A draft nobody approves within its
month lapses.

| # | Step | Check |
| --- | --- | --- |
| 1 | Read Meter's plan beside AWS's on the commitments screen, and why they differ | The plan names each line's program, family and Region, and what is not priced |
| 2 | Approve this month's tranche, with a note | Steps taken lists the approval with your name |
| 3 | Buy each line in the console as the payer, Savings Plans, Purchase Savings Plans: the program, term, payment option and hourly commitment the line names, an EC2 Instance line for its family in its Region | The console lists each new Savings Plan |
| 4 | Record the plan as bought, with a note | The plan reads Bought, not yet seen in full |
| 5 | Wait for the next inventory and plan runs, daily | The plan reads Verified, each line naming its commitment |

A line stays bought, and never reads as verified, when no commitment in the inventory matches it: the
same program, term and payment option, the same family and Region for an EC2 Instance line, an hourly
commitment within one percent of the line's, and a start after the approval. So a line bought with a
different amount, a different payment option, before the approval, or in an account outside the
organization is shown as not yet seen. Each commitment matches one line at most.
