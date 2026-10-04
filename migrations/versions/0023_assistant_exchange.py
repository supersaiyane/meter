"""What was asked of the assistant, and which of three things came back.

Revision ID: 0023_assistant_exchange
Revises: 0022_container_usage
Create Date: 2026-10-04

TASK-P7-003, P7 spec section 6.1. One row per question.

**The three outcomes are held apart here as well as in the entity.** An answer is
present if and only if the outcome is `ANSWERED`, a refusal's reason and gap if and
only if `REFUSED`, a typed cause if and only if `FAILED`. Each is a biconditional, the
shape 0020 uses for a quota's reason, because a one way check lets the other half
through: an answer stored beside a refusal is a row two screens would render as two
different things. `finops_core.domain.insight` refuses the same objects, and this is
the other door, a write that never went through the domain at all.

**The cause is one of the seven,** mirrored from `finops_core.errors` the way
`ERROR_TYPES` already is, so a generic failure cannot reach this table either. The
gap is one of five, mirrored from `Gap`.

**Spend needs a model.** Tokens and an estimated cost may be zero, and are on an
exchange that never reached one: a refusal on budget, a blocked secret, a deployment
with no model. They may not be above zero with no `model_id`, because spend nobody can
attribute is the line the platform cost screen cannot reconcile. There is no default
on any of the three. A writer that forgot them would otherwise record a confident zero,
which is the mistake a self metering product exists to catch.

**`question` is stored as typed.** No trimming, no case folding, because the wording is
the evidence when an answer turns out wrong. The one transformation is TASK-P7-013's:
a secret is redacted before the row is written, since a table of secrets in plain text
is a worse leak than the prompt would have been.

**`principal_id` is text and not a foreign key.** Principals are not persisted yet,
`finops_api.deps.get_access_context` says so, and a foreign key to an empty table would
refuse every row. It is the session's own identifier, which is what the access check
in TASK-P7-010 compares against.

**`asked_at` and `answered_at`, not `as_of` and `collected_at`.** An exchange records
our own work, like an ingest run. The `as_of` of every cited figure is inside
`citations`, beside the figure it dates.

Backward compatible, constraint 12: a new table that no earlier release reads or
writes. The downgrade drops it, as 0022 does, because the round trip test downgrades the
shared test database and a refusing downgrade there fails on any row an earlier test
left behind, which is what happened to 0018 on 2026-10-01.
"""

from __future__ import annotations

from alembic import op

revision = "0023_assistant_exchange"
down_revision = "0022_container_usage"
branch_labels = None
depends_on = None


_UP = (
    """
    CREATE TABLE IF NOT EXISTS assistant_exchange (
        exchange_id      UUID           PRIMARY KEY,
        tenant_id        UUID           NOT NULL REFERENCES tenant(tenant_id),
        principal_id     TEXT           NOT NULL,
        question         TEXT           NOT NULL,
        outcome          TEXT           NOT NULL,
        answer           TEXT,
        refusal_gap      TEXT,
        refusal_reason   TEXT,
        refusal_screen   TEXT,
        failure_cause    TEXT,
        failure_detail   TEXT,
        citations        JSONB          NOT NULL,
        tool_calls       JSONB          NOT NULL,
        model_id         TEXT,
        input_tokens     INTEGER        NOT NULL,
        output_tokens    INTEGER        NOT NULL,
        est_cost         NUMERIC(20, 10) NOT NULL,
        asked_at         TIMESTAMPTZ    NOT NULL,
        answered_at      TIMESTAMPTZ    NOT NULL
    )
    """,
    """
    ALTER TABLE assistant_exchange
        DROP CONSTRAINT IF EXISTS ck_assistant_exchange__outcome
    """,
    """
    ALTER TABLE assistant_exchange
        ADD CONSTRAINT ck_assistant_exchange__outcome
        CHECK (outcome IN ('ANSWERED', 'REFUSED', 'FAILED'))
    """,
    """
    ALTER TABLE assistant_exchange
        DROP CONSTRAINT IF EXISTS ck_assistant_exchange__answer_iff_answered
    """,
    """
    ALTER TABLE assistant_exchange
        ADD CONSTRAINT ck_assistant_exchange__answer_iff_answered
        CHECK ((outcome = 'ANSWERED') = (length(trim(coalesce(answer, ''))) > 0))
    """,
    # Twelve is REASON_MIN_LENGTH. A check constraint cannot read the constant, so the
    # figure is carried literally, as 0020 carries it.
    """
    ALTER TABLE assistant_exchange
        DROP CONSTRAINT IF EXISTS ck_assistant_exchange__reason_iff_refused
    """,
    """
    ALTER TABLE assistant_exchange
        ADD CONSTRAINT ck_assistant_exchange__reason_iff_refused
        CHECK ((outcome = 'REFUSED') = (length(trim(coalesce(refusal_reason, ''))) >= 12))
    """,
    """
    ALTER TABLE assistant_exchange
        DROP CONSTRAINT IF EXISTS ck_assistant_exchange__gap_iff_refused
    """,
    """
    ALTER TABLE assistant_exchange
        ADD CONSTRAINT ck_assistant_exchange__gap_iff_refused
        CHECK (
            (outcome = 'REFUSED') = (refusal_gap IS NOT NULL)
            AND (
                refusal_gap IS NULL
                OR refusal_gap IN ('tool', 'figure', 'scope', 'budget', 'secret')
            )
        )
    """,
    """
    ALTER TABLE assistant_exchange
        DROP CONSTRAINT IF EXISTS ck_assistant_exchange__screen_only_on_refusal
    """,
    """
    ALTER TABLE assistant_exchange
        ADD CONSTRAINT ck_assistant_exchange__screen_only_on_refusal
        CHECK (refusal_screen IS NULL OR outcome = 'REFUSED')
    """,
    """
    ALTER TABLE assistant_exchange
        DROP CONSTRAINT IF EXISTS ck_assistant_exchange__cause_iff_failed
    """,
    """
    ALTER TABLE assistant_exchange
        ADD CONSTRAINT ck_assistant_exchange__cause_iff_failed
        CHECK (
            (outcome = 'FAILED') = (failure_cause IS NOT NULL)
            AND (
                failure_cause IS NULL
                OR failure_cause IN (
                    'AccessDenied', 'Throttled', 'NotOptedIn', 'NoData',
                    'Unreachable', 'SchemaDrift', 'Misconfigured'
                )
            )
        )
    """,
    """
    ALTER TABLE assistant_exchange
        DROP CONSTRAINT IF EXISTS ck_assistant_exchange__detail_only_on_failure
    """,
    """
    ALTER TABLE assistant_exchange
        ADD CONSTRAINT ck_assistant_exchange__detail_only_on_failure
        CHECK (failure_detail IS NULL OR outcome = 'FAILED')
    """,
    # A citation is a figure in an answer. One stored beside a refusal is a figure the
    # screen would show under a sentence saying there was no figure to show.
    """
    ALTER TABLE assistant_exchange
        DROP CONSTRAINT IF EXISTS ck_assistant_exchange__citations_only_on_answer
    """,
    """
    ALTER TABLE assistant_exchange
        ADD CONSTRAINT ck_assistant_exchange__citations_only_on_answer
        CHECK (
            jsonb_typeof(citations) = 'array'
            AND jsonb_typeof(tool_calls) = 'array'
            AND (outcome = 'ANSWERED' OR citations = '[]'::jsonb)
        )
    """,
    """
    ALTER TABLE assistant_exchange
        DROP CONSTRAINT IF EXISTS ck_assistant_exchange__spend_not_negative
    """,
    """
    ALTER TABLE assistant_exchange
        ADD CONSTRAINT ck_assistant_exchange__spend_not_negative
        CHECK (input_tokens >= 0 AND output_tokens >= 0 AND est_cost >= 0)
    """,
    """
    ALTER TABLE assistant_exchange
        DROP CONSTRAINT IF EXISTS ck_assistant_exchange__spend_needs_a_model
    """,
    """
    ALTER TABLE assistant_exchange
        ADD CONSTRAINT ck_assistant_exchange__spend_needs_a_model
        CHECK (
            model_id IS NOT NULL
            OR (input_tokens = 0 AND output_tokens = 0 AND est_cost = 0)
        )
    """,
    """
    ALTER TABLE assistant_exchange
        DROP CONSTRAINT IF EXISTS ck_assistant_exchange__answered_after_asked
    """,
    """
    ALTER TABLE assistant_exchange
        ADD CONSTRAINT ck_assistant_exchange__answered_after_asked
        CHECK (answered_at >= asked_at)
    """,
    """
    ALTER TABLE assistant_exchange
        DROP CONSTRAINT IF EXISTS ck_assistant_exchange__who_and_what_not_blank
    """,
    """
    ALTER TABLE assistant_exchange
        ADD CONSTRAINT ck_assistant_exchange__who_and_what_not_blank
        CHECK (length(trim(principal_id)) > 0 AND length(trim(question)) > 0)
    """,
    # The exchanges list reads one person's newest first, and the budget sums a tenant's
    # month. Two different leading columns, so two indexes.
    """
    CREATE INDEX IF NOT EXISTS ix_assistant_exchange__principal
        ON assistant_exchange (tenant_id, principal_id, asked_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_assistant_exchange__tenant_month
        ON assistant_exchange (tenant_id, asked_at)
    """,
)


_DOWN = ("DROP TABLE IF EXISTS assistant_exchange",)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
