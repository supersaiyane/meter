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

1. **FOCUS names the columns.** Every new column takes its FOCUS 1.4 name in snake case and
   is read from AWS's FOCUS export where the export carries it, spec section 5.2.
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
| Status | Done 2026-10-07 |
| Implements | Spec section 12, the precondition for citing P10's tasks |
| Delivers | Tooling |
| Depends on | This plan approved, 2026-10-07 |
| Estimate | S |

**Acceptance criteria.**

- [x] `scripts/ci/check_memory.py` recognises `TASK-P10-001`, which its pattern of one digit
      skips today, with a test that a rotted P10 citation fails
- [x] `scripts/docs/sync.py` orders sub projects by number, so P10 follows P9 rather than P1,
      with a test

---

### TASK-P10-002: FOCUS 1.4's mandatory and invoice columns on the cost row

| Field | Value |
| --- | --- |
| Status | Done 2026-10-07 |
| Implements | Spec sections 4, 5.1, 5.2 and 6, FEAT-004 |
| Delivers | FEAT-004 at FOCUS 1.4's mandatory columns |
| Depends on | TASK-P10-001 |
| Estimate | M |

**Acceptance criteria.**

- [x] Migration 0030 adds `billing_account_name`, `billing_currency`, `charge_class`,
      `pricing_unit`, `service_provider_name`, `host_provider_name`, `invoice_id` and
      `invoice_detail_id` to `cost_focus_daily`, nullable, with `billing_currency` held to
      three capital letters by a constraint, and a down migration
- [x] It backfills `service_provider_name` and `host_provider_name` from `provider_name`,
      and `provider_name` and `publisher_name` stay and stay readable
- [x] The domain row and the export adapter read `billingaccountname`, `billingcurrency`,
      `chargeclass`, `pricingunit` and `invoiceid` where the export's table has them, asked of
      the catalog as the split columns are, and derive the two provider columns, each with a
      test from a fake row, present and absent
- [x] A test reads spec section 4's list of mandatory columns and fails if the row lacks one

---

### TASK-P10-003: billing periods and invoices

| Field | Value |
| --- | --- |
| Status | Done 2026-10-08 |
| Implements | Spec sections 5.3 and 6, FEAT-076 |
| Delivers | FEAT-076's source |
| Depends on | TASK-P10-002 |
| Estimate | M |

**Acceptance criteria.**

- [x] A port in `finops_core` names the read and its typed causes, with a fake in
      `finops_fakes`. `finops_core/ports/invoice.py`, `finops_fakes/invoices.py`, whose
      invoices are built from the bill's rows: one period matches, one is 2.50 over beside a
      Marketplace invoice, the running month has none. `tests/providers/fake/test_invoices.py`
- [x] An AWS adapter calls `ListInvoiceSummaries`, one billing period at a time, pages, keeps
      a credit memo with its original invoice, skips a payment receipt, turns AccessDenied and
      throttling into the typed causes through `translate`, and reads an unreadable amount,
      currency, period or date as SchemaDrift, never a zero, tested with a stubbed client,
      `tests/providers/aws/test_invoices.py`. Reworded on 2026-10-08: the criterion said
      through the credential broker, and the adapter is given the payer's client as
      `AwsBudgets` is; nothing in production builds either, which is ISS-182
- [x] Migration 0031 adds `billing_period` and `invoice_detail` with their constraints, each
      row carrying `as_of`, the issue date, and `collected_at`, and the guard holds both
      `PayerWide` before any route reads them, `tests/db/test_scope_guard.py`
- [x] A collector, `invoices`, with its cadence row, daily, in the migration and in
      `DEFAULT_SCHEDULE` with one reason, and its run in the ledger. Reworded on 2026-10-08:
      the read is one call at the payer, so a failure fails its own unit and is recorded by
      type, and no other collector's; it never writes a period Open because its invoices
      could not be read. `tests/ingest/collectors/test_invoices.py`
- [x] `invoicing:ListInvoiceSummaries` is added to the management account's organization
      reader role, `infra/terraform/management/main.tf`, and nothing that writes. Reworded on
      2026-10-08: the criterion named the member and hub stacks, and AWS issues invoices to
      the payer, so the management account is the only place they can be read

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
