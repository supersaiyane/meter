"""The AI provider organizations a tenant connected, P13 spec section 5.5, TASK-P13-004.

Read by the provider collectors on every run, so connecting an organization takes effect on the
next run and disconnecting one, `active` false, stops its reads without removing what was read.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text

from finops_core.domain.ai import ProviderAccount

CONNECTED = text(
    "SELECT provider, organization_id, name, key_secret_name FROM ai_provider_account "
    "WHERE tenant_id = :tenant AND provider = :provider AND active ORDER BY organization_id"
)


def connected(connection: Any, tenant_id: UUID, provider: str) -> tuple[ProviderAccount, ...]:
    """This tenant's active organizations of one provider, in a stable order."""
    rows = connection.execute(CONNECTED, {"tenant": tenant_id, "provider": provider}).mappings()
    return tuple(
        ProviderAccount(
            provider=row["provider"],
            organization_id=row["organization_id"],
            name=row["name"],
            key_secret_name=row["key_secret_name"],
        )
        for row in rows
    )
