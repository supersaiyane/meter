"""The code host a tenant connected, and where each Terraform state's fixes go. TASK-P15-003.

Revision ID: 0059_code_host
Revises: 0058_purchase_plan_match
Create Date: 2026-10-15

FEAT-091, P15 spec sections 5.1, 5.3 and 6, OPEN-13 and OPEN-42. `code_host_connection` is one row
per tenant: the host, the GitHub App's id and the Secrets Manager name of its private key, never
the key, with who connected it and when. A check holds the name to a `meter/<env>/codehost/` path,
so a row cannot point the worker at another secret, as `ai_provider_account` does for the AI path.
The installation is not stored: the worker asks GitHub which installation holds a repository on
each request, TASK-P15-002.

`repository_mapping` is one row per tenant and Terraform state, keyed by the state reference
FEAT-057 records in `resource_management`, naming the repository, the base branch and the folder
whose Terraform wrote that state. The checks hold what the adapter needs, constraint 11: a
repository written owner/name, a branch, and a folder relative to the repository's root that never
climbs out of it.

Both belong to the payer, ADR-0025. Backward compatible, constraint 12: new tables nothing old
reads. The downgrade removes them.
"""

from __future__ import annotations

from alembic import op

revision = "0059_code_host"
down_revision = "0058_purchase_plan_match"
branch_labels = None
depends_on = None

_CONNECTION = r"""
CREATE TABLE IF NOT EXISTS code_host_connection (
    tenant_id        UUID        NOT NULL REFERENCES tenant(tenant_id),
    host             TEXT        NOT NULL,
    app_id           TEXT        NOT NULL,
    key_secret_name  TEXT        NOT NULL,
    connected_by     TEXT        NOT NULL,
    connected_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_code_host_connection PRIMARY KEY (tenant_id),
    CONSTRAINT ck_code_host_connection__host CHECK (host IN ('github')),
    CONSTRAINT ck_code_host_connection__app CHECK (app_id ~ '^[A-Za-z0-9.]+$'),
    CONSTRAINT ck_code_host_connection__key
        CHECK (key_secret_name ~ '^meter/[a-z]+/codehost/[A-Za-z0-9/_+=.@-]+$')
)
"""

_MAPPING = r"""
CREATE TABLE IF NOT EXISTS repository_mapping (
    tenant_id        UUID        NOT NULL REFERENCES tenant(tenant_id),
    state_reference  TEXT        NOT NULL,
    repository       TEXT        NOT NULL,
    base_branch      TEXT        NOT NULL,
    folder           TEXT        NOT NULL DEFAULT '',
    set_by           TEXT        NOT NULL,
    set_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_repository_mapping PRIMARY KEY (tenant_id, state_reference),
    CONSTRAINT ck_repository_mapping__state CHECK (length(trim(state_reference)) > 0),
    CONSTRAINT ck_repository_mapping__repository
        CHECK (repository ~ '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'),
    CONSTRAINT ck_repository_mapping__branch CHECK (length(trim(base_branch)) > 0),
    CONSTRAINT ck_repository_mapping__folder CHECK (
        folder = '' OR (folder !~ '^/' AND folder !~ '/$' AND folder !~ '(^|/)\.\.?(/|$)'))
)
"""


def upgrade() -> None:
    op.execute(_CONNECTION)
    op.execute(_MAPPING)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS repository_mapping")
    op.execute("DROP TABLE IF EXISTS code_host_connection")
