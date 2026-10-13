# P14 Commitments: implementation plan

Date: 2026-10-13
Status: Approved by the owner on 2026-10-13 with OPEN-35 to OPEN-39 answered, in build
Spec: `docs/specs/2026-10-13-p14-commitments-design.md`
Depends on: P1, P9, P10 and P12. Proof against a real estate waits on ISS-002
Tasks: 10

Meter reports how much of each commitment was used and how much of the estate was covered, and
cannot say what the organization holds, when it ends, what the discounts saved, or what to buy
next. This sub project reads every commitment with its real term, puts the effective savings rate
at the top of the screen, shows what expires each month against a ladder, and drafts a purchase
plan beside AWS's recommendation for a person to approve, buy and see verified.

## How to work this plan

Same contract as P0 through P13. One task, one commit, `make verify` green before a merge.

**Three rules specific to P14.**

1. **Meter never buys.** No purchase, exchange or sale API is called, allow listed or granted, and
   a test of the Terraform and the relay fails the gate if one is. Constraint 6.
2. **A plan's figures are modelled and say so.** The baseline, the rate and the saving each carry
   their inputs, and a family with no rate is unpriced, never priced at zero.
3. **A commitment belongs to the payer.** Every new table is `PayerWide`, ADR-0025, and only a
   principal whose scope is global may approve or record a purchase.

## Wave overview

| Wave | Tasks | Delivers | Can start when |
| --- | --- | --- | --- |
| A. The payer path | 001 | Cost Explorer as the payer, ISS-294 | This plan approved |
| B. What is held | 002, 003 | The inventory, every reservable service | A |
| C. What it saved and when it ends | 004, 005 | The savings rate, the policy and the calendar | B |
| D. What to buy | 006, 007, 008 | AWS's recommendation, Meter's plan, approval and verification | C |
| E. The screen and the proof | 009, 010 | The commitments screen, the local stack, the exit criteria | D |

Modelled at the pace of P13: seven tasks of size M and three of size S, about nine working days.

---

### TASK-P14-001: Cost Explorer's commitment reads, as the payer

| Field | Value |
| --- | --- |
| Status | Done 2026-10-13 |
| Implements | Spec section 5.8, ISS-294 |
| Delivers | FEAT-086 |
| Depends on | Nothing |
| Estimate | S |

**Acceptance criteria.**

- [x] The management stack's organization reader role gains the Cost Explorer commitment reads,
      use, coverage and the two purchase recommendations, and nothing that buys, held by a test
- [x] `CostExplorerCommitmentReport` assumes that role through the Cost Explorer endpoint the hub
      already has, and a missing payer setting reads as Misconfigured
- [x] `make first-contact` probes the commitment reads as the payer
- [x] FEAT-024 and the deployment document say what changed

**Delivered 2026-10-13.** `AwsCredentialBroker.payer_session` assumes the organization reader role
with the ExternalId, through STS in the hub's first collection Region, cached apart from the
management account's collector role; `finops_providers.aws.reach.payer_client` makes a client on it
on first use; the commitment collector and, because it had the same defect, account discovery are
bound to it, ISS-294 and ISS-296. `infra/terraform/management/main.tf` grants the five Cost Explorer
commitment reports and AWS's two purchase recommendations, and
`tests/contract/test_no_commitment_purchases.py` holds that grant exact and fails the build on any
role, relay call or module that could buy a commitment. First contact probes both as the payer.
Nothing applied, ISS-002.

---

### TASK-P14-002: the inventory, Savings Plans, EC2 and RDS

| Field | Value |
| --- | --- |
| Status | Done 2026-10-13 |
| Implements | Spec sections 5.3, 5.5 and 6, OPEN-37, OPEN-39, ADR-0037 |
| Delivers | FEAT-086 |
| Depends on | TASK-P14-001 |
| Estimate | M |

**Acceptance criteria.**

- [x] A migration creates `commitment_inventory` with its checks, and installs the
      `commitment_inventory` cadence for existing tenants
- [x] A port, and adapters for Savings Plans through the relay, EC2 reservations through the EC2
      endpoint, and RDS reservations through the relay, each typed for every failure
- [x] The relay's allow list and the member collector role gain exactly the three reads
- [x] The collector is scheduled, composed in both modes and has a fake estate with a commitment
      ending next month and an account that refuses

**Delivered 2026-10-13.** `HeldCommitment` in `finops_core/domain/commitments.py` and the
`CommitmentHoldings` port; `finops_providers/aws/commitment_inventory.py`, which reads Savings Plans
and RDS reservations through the relay and EC2 reservations through the EC2 endpoint, each as the
account's collector role, every page on both paths, failures typed; migration
`0054_commitment_inventory` with its checks and the cadence for existing tenants; the collector,
which reads Savings Plans only in the first collection Region's unit and restates only the scope it
read; the relay's allow list and the member role gain the three reads and nothing that buys; a fake
estate with a plan ending in three weeks, a retired plan and the refusing account; both
compositions; and three first contact probes, the relayed ones as the member account. Nothing
applied, ISS-002.

---

### TASK-P14-003: the inventory, every other reservable service

| Field | Value |
| --- | --- |
| Status | Done 2026-10-13 |
| Implements | Spec section 5.3, OPEN-37 |
| Delivers | FEAT-086 |
| Depends on | TASK-P14-002 |
| Estimate | S |

**Acceptance criteria.**

- [x] Adapters for ElastiCache, OpenSearch, Redshift and MemoryDB reservations through the relay
- [x] The relay's allow list and the member collector role gain exactly the four reads
- [x] DynamoDB reserved capacity is recorded as unreadable, ISS-295, and FEAT-086 says so

**Delivered 2026-10-13.** The adapter's per service readers became one, driven by `RESERVED`, a
table of where each reserved service keeps its identifier, type, count and payment option; EC2 and
RDS moved onto it unchanged, and ElastiCache, OpenSearch, Redshift and MemoryDB joined through the
relay, ADR-0037. The relay's allow list and the member collector role gain exactly the four reads,
and first contact probes each as the member account. `UNREADABLE` names DynamoDB reserved capacity,
which no API reads, ISS-295. The fake estate holds three ElastiCache nodes. Nothing applied,
ISS-002.

---

### TASK-P14-004: the effective savings rate, measured from the bill

| Field | Value |
| --- | --- |
| Status | Done 2026-10-13 |
| Implements | Spec section 5.7 |
| Delivers | FEAT-087 |
| Depends on | Nothing |
| Estimate | S |

**Acceptance criteria.**

- [x] `GET /v1/commitments/savings-rate` returns the rate by month with Effective Cost, List Cost
      and the lines without a List Cost, each measured
- [x] A month whose lines carry no List Cost has no rate and says why, never a rate of zero
- [x] The fake bill carries List Cost on its usage lines, so the demo shows a rate

**Delivered 2026-10-13.** `finops_query/savings_rate.py`, the rate over the lines carrying a List
Cost, none with the reason where no line does; `CostRepository.savings_rate_months`, the cloud bill's
usage lines by billing month with both timestamps; and `finops_api/routes/commitments.py`, P14's
router, with `GET /v1/commitments/savings-rate`, exportable and scoped by account as the bill is. The
fake bill already carries List Cost on its usage lines, 583 of the demo's 715 cloud lines on
2026-10-13, measured; the split cost lines carry none and are counted as left out. The overview's
tile still reads Cost Explorer's sum, which offers List Cost only when every line carries it, so it
reads the new route from TASK-P14-009 and the two screens cannot disagree.

---

### TASK-P14-005: the policy and the renewal calendar

| Field | Value |
| --- | --- |
| Status | Done 2026-10-13 |
| Implements | Spec sections 5.4 and 8, OPEN-38 |
| Delivers | FEAT-088 |
| Depends on | TASK-P14-002 |
| Estimate | M |

**Acceptance criteria.**

- [x] A migration creates `commitment_policy`, installed for new tenants and for every existing one
      with the cautious default
- [x] `GET` and `PUT /v1/commitments/policy`, a change requiring a reason and a global principal,
      audited
- [x] `GET /v1/commitments/calendar` returns twelve months of expiring commitment with each month's
      share, flagging a month above the ladder limit

**Delivered 2026-10-13.** `CommitmentPolicy` and `DEFAULT_POLICY` in the domain; migration
`0055_commitment_policy` with a check on every bound and the default for every tenant;
`install_default_policy` and `policy_for` in `finops_ingest/commitment_policy.py`, the seed
installing it beside the schedule; `finops_query/commitment_calendar.py`; the inventory and policy
repositories, the change audited; and `GET /v1/commitments/inventory`, `GET /v1/commitments/calendar`
and `GET` and `PUT /v1/commitments/policy`, each answering a narrowed reader with a 404 that says
commitments need the payer, and refusing a narrowed change with a 403 audited DENIED. An erasure keeps
the policy and replaces the name on it, and `docs/09-DATA-CLASSIFICATION.md` says so.

---

### TASK-P14-006: AWS's purchase recommendations

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec sections 5.1 and 7, OPEN-35 |
| Delivers | FEAT-089 |
| Depends on | TASK-P14-001, TASK-P14-005 |
| Estimate | M |

**Acceptance criteria.**

- [ ] A migration creates `purchase_recommendation` and installs the collector's cadence, with its
      modelled cost per run
- [ ] An adapter reads both recommendation calls as the payer for the policy's term and payment
      option, every failure typed
- [ ] The collector is scheduled, composed in both modes and has a fake

---

### TASK-P14-007: Meter's purchase plan

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec sections 5.6 and 6 |
| Delivers | FEAT-089 |
| Depends on | TASK-P14-005, TASK-P14-006 |
| Estimate | M |

**Acceptance criteria.**

- [ ] `finops_query` holds the plan's arithmetic, pure: the steady baseline, P9's rates, the target
      and the ladder, every figure modelled with its inputs
- [ ] A family with no P9 rate is unpriced and named, never priced at zero; a day the bill does not
      hold is not a day of zero
- [ ] A migration creates the plan tables; the `purchase_plan` collector drafts a plan and lapses
      an old draft
- [ ] `GET /v1/commitments/plans` returns Meter's plan beside AWS's recommendations, with the
      difference in words

---

### TASK-P14-008: approval, the purchase recorded, and verification

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 5.2, OPEN-36 |
| Delivers | FEAT-090 |
| Depends on | TASK-P14-007 |
| Estimate | M |

**Acceptance criteria.**

- [ ] `POST` approve, bought and withdraw, each an event with the principal, the time and a note,
      for a global principal only; a narrowed principal is refused
- [ ] A transition out of order is refused by the database as well as the API
- [ ] The plan collector matches a bought line to a new commitment and verifies the plan, and a
      line matched to nothing stays bought, shown as not yet seen

---

### TASK-P14-009: the commitments screen

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 8 |
| Delivers | FEAT-087, FEAT-088, FEAT-089, FEAT-090 |
| Depends on | TASK-P14-004 to TASK-P14-008 |
| Estimate | M |

**Acceptance criteria.**

- [ ] The commitments screen opens on the effective savings rate and gains the inventory, the
      calendar and the plans, each panel with its freshness
- [ ] The plans panel offers approve, bought and withdraw to a principal who may take them, and
      says why to one who may not
- [ ] Every figure says measured or modelled; unit tests and a Playwright journey

---

### TASK-P14-010: the local stack, first contact, proof and documents

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 13 |
| Delivers | The exit criteria, measured, and the record |
| Depends on | TASK-P14-001 to TASK-P14-009 |
| Estimate | M |

**Acceptance criteria.**

- [ ] The seeded demo and the local stack carry the inventory, the rate, the calendar and a plan
- [ ] `make first-contact` probes each new read, and a runbook names the owner's steps
- [ ] Every exit criterion in spec section 13 met, each with its evidence
- [ ] FEAT-086 to FEAT-090 say what was built; the register, `project_map.md` and the checkpoint
      updated, and `make check-docs` clean
