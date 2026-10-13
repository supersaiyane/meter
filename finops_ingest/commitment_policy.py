"""A tenant's commitment policy: the cautious default installed, and the policy read. FEAT-088.

TASK-P14-005, OPEN-38. Beside `install_default_schedule`, because both are what a tenant starts
with: migration 0055 gave every tenant that existed the default, and a tenant made after it gets
the same from here. The purchase plan collector reads the policy through `policy_for`, and a tenant
with no row plans under the default rather than under nothing.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text

from finops_core.domain.commitments import DEFAULT_POLICY, DEFAULT_POLICY_REASON, CommitmentPolicy

INSTALL = text(
    "INSERT INTO commitment_policy (tenant_id, target_coverage, term_years, payment_option, "
    "ladder_limit, reason, updated_by) VALUES (:tenant, :coverage, :term, :payment, :ladder, "
    ":reason, :by) ON CONFLICT (tenant_id) DO NOTHING"
)

READ = text(
    "SELECT target_coverage, term_years, payment_option, ladder_limit FROM commitment_policy "
    "WHERE tenant_id = :tenant"
)


def install_default_policy(connection: Any, tenant_id: UUID, *, updated_by: str) -> None:
    """Give the tenant the cautious default, leaving a policy it already has alone."""
    connection.execute(
        INSTALL,
        {
            "tenant": tenant_id,
            "coverage": DEFAULT_POLICY.target_coverage,
            "term": DEFAULT_POLICY.term_years,
            "payment": DEFAULT_POLICY.payment_option,
            "ladder": DEFAULT_POLICY.ladder_limit,
            "reason": DEFAULT_POLICY_REASON,
            "by": updated_by,
        },
    )


def policy_for(connection: Any, tenant_id: UUID) -> CommitmentPolicy:
    """The tenant's policy, or the default where it has none."""
    row = connection.execute(READ, {"tenant": tenant_id}).one_or_none()
    if row is None:
        return DEFAULT_POLICY
    return CommitmentPolicy(
        target_coverage=row[0], term_years=row[1], payment_option=row[2], ladder_limit=row[3]
    )
