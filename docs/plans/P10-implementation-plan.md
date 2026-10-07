# P10 Proven numbers, FOCUS 1.4 and invoice reconciliation: implementation plan

Date: 2026-10-07
Status: Approved by the owner on 2026-10-07 as priority 2 of `next-in-scope.txt`, CHG-0122
Spec: `docs/specs/2026-10-07-p10-proven-numbers-design.md`
Depends on: P1 delivered. Proof against a real invoice waits on ISS-002, ISS-003 and TASK-P9-001
Tasks: 6

Meter says how far each figure can be trusted and has never checked a total against the bill.
This sub project gives the cost row the columns FOCUS 1.4 makes mandatory and the two that
tie a row to its invoice, reads AWS's invoices, and shows how closely Meter's billed cost
matches each one. It runs before P9, by the owner's priority of 2026-10-07.

## How to work this plan

Same contract as P0 through P9. One task, one commit, `make verify` green before a merge.

**Four rules specific to P10.**

1. **FOCUS names the columns.** Every new column takes its FOCUS 1.4 name in snake case, and
   its meaning from AWS's published mapping for its own FOCUS 1.2 export, spec section 5.2.
2. **Add, backfill, drop later.** Nothing is renamed or dropped in P10. `provider_name` and
   `publisher_name` stay readable until a release after it, constraint 12.
3. **A comparison is a state before it is a number.** Every comparison has one of the states
   in spec section 5.4, and a failure is never a zero.
4. **An invoice is the payer's.** Only a reader whose scope covers the whole payer sees one,
   spec section 5.5.

## Wave overview

| Wave | Tasks | Delivers | Can start when |
| --- | --- | --- | --- |
| A. Tooling | 001 | Two digit sub projects in the memory gate and the generated tables | This plan approved, 2026-10-07 |
| B. The columns | 002 | FOCUS 1.4's mandatory and invoice columns on the cost row | A |
| C. The invoices | 003 | Billing periods and invoices read, kept and dated | B |
| D. The comparison | 004, 005 | The comparison, its route, its screen and its tile | C |
| E. Proof and documents | 006 | Exit criteria measured, constraint 2 and the documents updated | All |

---

### TASK-P10-001: two digit sub projects in the tooling

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 12, the precondition for citing P10's tasks |
| Delivers | Tooling |
| Depends on | This plan approved, 2026-10-07 |
| Estimate | S |

**Acceptance criteria.**

- [ ] `scripts/ci/check_memory.py` recognises `TASK-P10-001`, which its pattern of one digit
      skips today, with a test that a rotted P10 citation fails
- [ ] `scripts/docs/sync.py` orders sub projects by number, so P10 follows P9 rather than P1,
      with a test

---

### TASK-P10-002: FOCUS 1.4's mandatory and invoice columns on the cost row

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec sections 4, 5.1, 5.2 and 6, FEAT-004 |
| Delivers | FEAT-004 at FOCUS 1.4's mandatory columns |
| Depends on | TASK-P10-001 |
| Estimate | M |

**Acceptance criteria.**

- [ ] Migration 0030 adds `billing_account_name`, `billing_currency`, `charge_class`,
      `pricing_unit`, `service_provider_name`, `host_provider_name`, `invoice_id` and
      `invoice_detail_id` to `cost_focus_daily`, nullable, with `billing_currency` held to
      three capital letters by a constraint, and a down migration
- [ ] It backfills `service_provider_name` from `publisher_name` and `host_provider_name`
      from `provider_name`, and both old columns stay and stay readable
- [ ] The domain row and the CUR 2.0 normalisation fill each new column by AWS's mapping,
      each with a test from a fake row
- [ ] A test reads spec section 4's list of mandatory columns and fails if the row lacks one

---

### TASK-P10-003: billing periods and invoices

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec sections 5.3 and 6, FEAT-076 |
| Delivers | FEAT-076's source |
| Depends on | TASK-P10-002 |
| Estimate | M |

**Acceptance criteria.**

- [ ] A port in `finops_core` names the read and its typed causes, with a fake in
      `finops_fakes`
- [ ] An AWS adapter calls `ListInvoiceSummaries` through the credential broker, pages, keeps
      a credit memo with its original invoice, and turns AccessDenied, throttling and a
      missing account into the typed causes, tested with a stubbed client
- [ ] Migration 0031 adds `billing_period` and `invoice_detail` with their constraints, each
      row carrying `as_of`, the issue date, and `collected_at`
- [ ] A collector, `invoices`, with its cadence row, daily, its run in the ledger, and
      partial failure that never fails the run
- [ ] `invoicing:ListInvoiceSummaries` is added to the reader role in the member and hub
      stacks, and nothing that writes

---

### TASK-P10-004: the comparison and its route

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec sections 5.4, 5.5 and 7, FEAT-076 |
| Delivers | FEAT-076's figure |
| Depends on | TASK-P10-003 |
| Estimate | M |

**Acceptance criteria.**

- [ ] For each invoice, before tax and tax apart, in its currency, every state in spec
      section 5.4, with the tolerance a named constant and its reason
- [ ] `GET /api/v1/cost/reconciliation?period=` in the envelope, exportable, with `as_of`
      and `collected_at`
- [ ] The guard's `PayerWide` rule on both tables, and a narrowed reader refused by type,
      asserted with two principals against the database

---

### TASK-P10-005: the screen and the Overview tile

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 7, FEAT-076 |
| Delivers | FEAT-076's surface |
| Depends on | TASK-P10-004 |
| Estimate | M |

**Acceptance criteria.**

- [ ] An Invoice reconciliation screen at `/report/reconciliation`, every state in words,
      the difference beside each mismatch, labelled measured
- [ ] A Matches the invoice tile on the FinOps practitioner's Overview for the last period
      with an issued invoice, linking to the screen
- [ ] The screen in the rail's sweeps for axe and widths, and a journey through it

---

### TASK-P10-006: proof and documents

| Field | Value |
| --- | --- |
| Status | Not started |
| Implements | Spec section 12, `docs/03-CHANGE-CONTROL.md` |
| Delivers | The record |
| Depends on | TASK-P10-001 to TASK-P10-005 |
| Estimate | S |

**Acceptance criteria.**

- [ ] Every exit criterion in spec section 12 met, each with its evidence
- [ ] Constraint 2 in `CLAUDE.md` names FOCUS 1.4, and FEAT-004 and FEAT-076 say what was
      built
- [ ] The register, `project_map.md` and the checkpoint updated, and `make check-docs` clean
