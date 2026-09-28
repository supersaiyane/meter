"""A seventh cause, for a value this deployment set that does not exist.

Revision ID: 0018_misconfigured_cause
Revises: 0017_budget
Create Date: 2026-09-28

ISS-215, decided in ADR-0026. Before this, a configuration aggregator name that does not
exist and a Terraform state path that does not exist both arrived as `SchemaDrift`. That
is loud and is never rendered as a zero, so nothing was ever hidden by it. It was the
wrong word: it told an operator their schema had drifted and sent them looking for an API
change, when the fix was one line of their own settings.

**Widening a check constraint is the backward compatible direction, which is why this is
one migration and not three.** Constraint 12 asks that old and new task definitions run
against the same schema during a rolling deploy. Old code never writes `Misconfigured`, so
it keeps satisfying the wider constraint; new code writes it and the wider constraint
admits it. Nothing is backfilled because nothing existing is wrong: rows already written as
`SchemaDrift` were correct under the vocabulary of the day, and rewriting history to a
cause the collector never chose would be inventing a judgement nobody made.

**Three constraints, because the vocabulary is held in three places.** `ingest_run` and
`sync_error` since 0001, and `graph_coverage` since 0014, which also admits
`NotYetAttempted` and keeps it. A seventh value reaching one table and not another is how a
collector writes a row it cannot later read back.

The taxonomy staying closed is the point of all three. A new cause cannot reach the
database without a migration, which is what stops every future failure quietly becoming
generic.
"""

from __future__ import annotations

from alembic import op

revision = "0018_misconfigured_cause"
down_revision = "0017_budget"
branch_labels = None
depends_on = None

#: The six, plus the seventh. Spelled out rather than imported from the application, because a
#: migration reads the schema as it was and an import would make this file change meaning the
#: next time the tuple does.
CAUSES = (
    "AccessDenied",
    "Throttled",
    "NotOptedIn",
    "NoData",
    "Unreachable",
    "SchemaDrift",
    "Misconfigured",
)

#: `graph_coverage` carries one more: a slice nothing has tried yet is not a failure.
COVERAGE_CAUSES = (*CAUSES, "NotYetAttempted")


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_UP = (
    """
    ALTER TABLE ingest_run DROP CONSTRAINT IF EXISTS ck_ingest_run__error_type_valid
    """,
    f"""
    ALTER TABLE ingest_run
        ADD CONSTRAINT ck_ingest_run__error_type_valid
        CHECK (error_type IS NULL OR error_type IN ({_quoted(CAUSES)}))
    """,
    """
    ALTER TABLE sync_error DROP CONSTRAINT IF EXISTS ck_sync_error__type_valid
    """,
    f"""
    ALTER TABLE sync_error
        ADD CONSTRAINT ck_sync_error__type_valid
        CHECK (error_type IN ({_quoted(CAUSES)}))
    """,
    """
    ALTER TABLE graph_coverage DROP CONSTRAINT IF EXISTS ck_graph_coverage__cause_known
    """,
    f"""
    ALTER TABLE graph_coverage
        ADD CONSTRAINT ck_graph_coverage__cause_known
        CHECK (cause IS NULL OR cause IN ({_quoted(COVERAGE_CAUSES)}))
    """,
)

#: The six, for the way back. A downgrade is only safe once no row uses the seventh, which is
#: why each statement below refuses rather than deletes: dropping rows to satisfy a constraint
#: would destroy the record of why a collection failed in order to make a schema change succeed.
_SIX = CAUSES[:-1]

_DOWN = (
    """
    DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM sync_error WHERE error_type = 'Misconfigured')
        OR EXISTS (SELECT 1 FROM ingest_run WHERE error_type = 'Misconfigured')
        OR EXISTS (SELECT 1 FROM graph_coverage WHERE cause = 'Misconfigured') THEN
            RAISE EXCEPTION
                'rows still record Misconfigured. Reclassify or remove them before '
                'downgrading: this migration will not delete a record of a failure to '
                'make a schema change succeed.';
        END IF;
    END $$
    """,
    "ALTER TABLE ingest_run DROP CONSTRAINT IF EXISTS ck_ingest_run__error_type_valid",
    f"""
    ALTER TABLE ingest_run
        ADD CONSTRAINT ck_ingest_run__error_type_valid
        CHECK (error_type IS NULL OR error_type IN ({_quoted(_SIX)}))
    """,
    "ALTER TABLE sync_error DROP CONSTRAINT IF EXISTS ck_sync_error__type_valid",
    f"""
    ALTER TABLE sync_error
        ADD CONSTRAINT ck_sync_error__type_valid
        CHECK (error_type IN ({_quoted(_SIX)}))
    """,
    "ALTER TABLE graph_coverage DROP CONSTRAINT IF EXISTS ck_graph_coverage__cause_known",
    f"""
    ALTER TABLE graph_coverage
        ADD CONSTRAINT ck_graph_coverage__cause_known
        CHECK (cause IS NULL OR cause IN ({_quoted((*_SIX, "NotYetAttempted"))}))
    """,
)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWN:
        op.execute(statement)
