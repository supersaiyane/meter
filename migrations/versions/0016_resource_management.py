"""Which file manages a resource, recorded only where we found one.

Revision ID: 0016_resource_management
Revises: 0015_commitment_action
Create Date: 2026-09-26

FEAT-057, TASK-P4-013.

**The table stores presence and never absence, and that is the whole design.** A state file
names the resources it owns and does not name the ones it does not. Nothing in it says whether
it is the only state file in the organization. So a row here means we found a resource in
state; no row means we did not find it, which is a different fact from nobody managing it.

`ManagementState.UNMANAGED` is therefore never stored. It is derived at read time from two
things that are both about our own configuration: a declaration that the backends we read are
the whole of the infrastructure as code for an account, and a run in which all of them were
actually read. Storing it would freeze a judgement made under yesterday's configuration into a
row that outlives it, and somebody would act on it after adding a workspace.

**Its own table rather than columns on `topology_node`, and ADR-0024 is why.** One collector
owns a slice's graph: a second writer to `topology_node` would race the inventory collector's
run scoped retraction, which removes what the provider withdrew, and the retraction would
delete what the second writer had just put there. A separate table also lets this read on its
own cadence, which it needs, because the state of a bucket and the state of an estate change
for different reasons.

**No foreign key to `topology_node`.** Terraform routinely manages resources Meter has never
inventoried, and a key would refuse exactly those rows. The collector does resolve each one to
an account before writing, and counts the ones it cannot place, because a managed resource with
no node is evidence about our inventory rather than a row to discard. The same reasoning
0014 gives for `topology_edge.to_node_id`.

**`sub_account_id` is on the row so the guard has something to scope by.** It is resolved from
the node the resource joined to, not parsed out of the ARN, so a row exists only where the
account is known rather than where a string looked like one.
"""

from __future__ import annotations

from alembic import op

revision = "0016_resource_management"
down_revision = "0015_commitment_action"
branch_labels = None
depends_on = None

_UP = (
    """
    CREATE TABLE IF NOT EXISTS resource_management (
        management_id UUID PRIMARY KEY,
        tenant_id UUID NOT NULL REFERENCES tenant(tenant_id),
        ingest_run_id UUID NOT NULL,
        sub_account_id TEXT NOT NULL,
        provider_id TEXT NOT NULL,
        address TEXT NOT NULL,
        state_reference TEXT NOT NULL,
        as_of TIMESTAMPTZ NOT NULL,
        collected_at TIMESTAMPTZ NOT NULL
    )
    """,
    # One current row per resource. A resource moved between state files gets its row updated
    # rather than gaining a second, because two addresses for one resource would let a reader
    # open a pull request against whichever the query happened to return first.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_resource_management__provider_id
        ON resource_management (tenant_id, provider_id)
    """,
    # An address with no module path and no resource name names nothing, and FEAT-040 would
    # open a pull request against it. Constraint 11: application code being the only thing
    # preventing a bad row means the bad row will eventually exist.
    """
    ALTER TABLE resource_management
        ADD CONSTRAINT ck_resource_management__address_is_not_empty
        CHECK (length(trim(address)) > 0)
    """,
    # The location has to be findable by a person. A row saying a resource is managed by
    # something unnamed is a row nobody can act on.
    """
    ALTER TABLE resource_management
        ADD CONSTRAINT ck_resource_management__reference_is_not_empty
        CHECK (length(trim(state_reference)) > 0)
    """,
    # The read is by resource, from the entity page, and by account for the guard.
    """
    CREATE INDEX IF NOT EXISTS ix_resource_management__account
        ON resource_management (tenant_id, sub_account_id)
    """,
)


def upgrade() -> None:
    for statement in _UP:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS resource_management")
