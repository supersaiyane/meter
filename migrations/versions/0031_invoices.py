"""The billing periods and the invoices AWS issued for them.

Revision ID: 0031_invoices
Revises: 0030_focus_1_4_columns
Create Date: 2026-10-07

TASK-P10-003, FEAT-076, ADR-0034, P10 spec sections 5.3 and 6.

FOCUS 1.4's Billing Period and Invoice Detail datasets, at the grain AWS gives: the Invoicing
API returns whole invoices, so one invoice is one detail row and its detail id is its invoice
id. Both tables carry `ingest_run_id` and the two timestamps, constraint 10, because an invoice
read from a provider is a fact with a provenance like every other row here.

**Nothing derived is stored.** Not Meter's sum over the cost rows, not the difference, not the
state. The comparison is computed when it is read, TASK-P10-004, so it cannot drift from either
side, and a stored difference would be stale the moment a late row arrived.

**One billing period row per tenant and month.** A period is Closed once an invoice for it has
been issued, the reading the domain module records, and Open until then. It carries no billing
account: the source names the payer only on an invoice, and an open period has none yet.

**Payer wide, ADR-0025.** An invoice totals every account under the payer, so the guard scopes
both tables as it scopes `budget`, and a narrowed reader reads nothing rather than a total that
includes accounts they cannot see.

**The amounts are not held to add up.** AWS documents `TotalAmount` and the amount before tax
but not the arithmetic between them once fees and discounts are in the breakdown, so a
constraint that the total is the two summed could refuse a real invoice. Each is held not
null and stored as read.

Backward compatible, constraint 12: two new tables nothing old reads and one new schedule row
nothing old runs. The downgrade drops what this adds.
"""

from __future__ import annotations

from alembic import op

revision = "0031_invoices"
down_revision = "0030_focus_1_4_columns"
branch_labels = None
depends_on = None

#: The cadence row this migration installs for every tenant that exists. A copy of the
#: `invoices` entry in `finops_ingest.registry.DEFAULT_SCHEDULE`, which installs it for a
#: tenant onboarded later.
_CADENCE_SECONDS = 86400
_REASON = (
    "Daily, because AWS issues an invoice once a month and a credit memo rarely, so a daily "
    "read finds each within a day of its issue. A run is one ListInvoiceSummaries per billing "
    "period at the payer, modelled at no cost until a real bill shows otherwise. ADR-0012, "
    "constraint 9 and FEAT-076."
)
_COST_PER_RUN = "0"

_UP = (
    # ------------------------------------------------------------------ billing periods
    """
    CREATE TABLE IF NOT EXISTS billing_period (
        billing_period_pk     UUID         PRIMARY KEY,
        tenant_id             UUID         NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id         UUID         NOT NULL,
        billing_period_start  DATE         NOT NULL,
        billing_period_end    DATE         NOT NULL,
        billing_period_status TEXT         NOT NULL,
        as_of                 TIMESTAMPTZ  NOT NULL,
        collected_at          TIMESTAMPTZ  NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_period__identity
        ON billing_period (tenant_id, billing_period_start)
    """,
    # FOCUS 1.4's two values, in its own capitalisation.
    """
    ALTER TABLE billing_period
        ADD CONSTRAINT ck_billing_period__status
        CHECK (billing_period_status IN ('Open', 'Closed'))
    """,
    """
    ALTER TABLE billing_period
        ADD CONSTRAINT ck_billing_period__period_is_a_period
        CHECK (billing_period_end > billing_period_start)
    """,
    """
    ALTER TABLE billing_period
        ADD CONSTRAINT ck_billing_period__collected_after_true
        CHECK (collected_at >= as_of)
    """,
    # ------------------------------------------------------------------ invoices
    """
    CREATE TABLE IF NOT EXISTS invoice_detail (
        invoice_detail_pk       UUID           PRIMARY KEY,
        tenant_id               UUID           NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id           UUID           NOT NULL,
        invoice_id              TEXT           NOT NULL,
        invoice_detail_id       TEXT           NOT NULL,
        invoice_type            TEXT           NOT NULL,
        original_invoice_id     TEXT,
        billing_account_id      TEXT           NOT NULL,
        billing_period_start    DATE           NOT NULL,
        billing_period_end      DATE           NOT NULL,
        invoice_issuer_name     TEXT           NOT NULL,
        billing_currency        TEXT           NOT NULL,
        billed_cost_before_tax  NUMERIC(20, 10) NOT NULL,
        tax                     NUMERIC(20, 10) NOT NULL,
        billed_cost             NUMERIC(20, 10) NOT NULL,
        issued_at               TIMESTAMPTZ    NOT NULL,
        due_date                DATE,
        as_of                   TIMESTAMPTZ    NOT NULL,
        collected_at            TIMESTAMPTZ    NOT NULL
    )
    """,
    # An invoice id is AWS's and unique to the payer. A credit memo is its own row with its
    # own id, so a correction never overwrites what it corrects.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_invoice_detail__identity
        ON invoice_detail (tenant_id, invoice_id)
    """,
    """
    ALTER TABLE invoice_detail
        ADD CONSTRAINT ck_invoice_detail__type
        CHECK (invoice_type IN ('INVOICE', 'CREDIT_MEMO'))
    """,
    # A credit memo that does not name what it corrects cannot be shown beside it, and would be
    # netted against the period as if it were a second invoice.
    """
    ALTER TABLE invoice_detail
        ADD CONSTRAINT ck_invoice_detail__credit_memo_names_original
        CHECK (invoice_type = 'INVOICE' OR length(trim(coalesce(original_invoice_id, ''))) > 0)
    """,
    """
    ALTER TABLE invoice_detail
        ADD CONSTRAINT ck_invoice_detail__billing_currency_iso
        CHECK (billing_currency ~ '^[A-Z]{3}$')
    """,
    """
    ALTER TABLE invoice_detail
        ADD CONSTRAINT ck_invoice_detail__period_is_a_period
        CHECK (billing_period_end > billing_period_start)
    """,
    """
    ALTER TABLE invoice_detail
        ADD CONSTRAINT ck_invoice_detail__collected_after_true
        CHECK (collected_at >= as_of)
    """,
    # The read is every invoice for a period, which is the only shape the screen asks for.
    """
    CREATE INDEX IF NOT EXISTS ix_invoice_detail__period
        ON invoice_detail (tenant_id, billing_period_start)
    """,
    # ------------------------------------------------------------------ the cadence
    f"""
    INSERT INTO collector_schedule
        (tenant_id, collector, cadence_seconds, reason, est_cost_per_run, updated_by, runs_in)
    SELECT tenant_id, 'invoices', {_CADENCE_SECONDS}, '{_REASON}', {_COST_PER_RUN},
           'migration 0031_invoices', 'worker'
    FROM tenant
    ON CONFLICT (tenant_id, collector) DO NOTHING
    """,
)


_DOWN = (
    "DELETE FROM collector_schedule WHERE collector = 'invoices'",
    "DROP TABLE IF EXISTS invoice_detail",
    "DROP TABLE IF EXISTS billing_period",
)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
