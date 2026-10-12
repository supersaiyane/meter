"""A tenant's active cloud accounts, the ones collection reads. TASK-P12-004.

One query for the two places that need it: the dispatcher, which fans each account scoped
collector out over these accounts, and the inventory's AWS binder, which reads each of them in
every Region. Two queries would let the two disagree about which accounts a tenant has.
"""

from __future__ import annotations

from typing import Any, Final

from sqlalchemy import text

from finops_core.domain.account import AccountKey, AccountStatus, Provider

ACTIVE: Final = (
    "SELECT account_id FROM cloud_account"
    " WHERE tenant_id = :tenant AND provider = :provider AND status = :status"
    " ORDER BY account_id"
)


def active_accounts(connection: Any, tenant_id: Any) -> tuple[AccountKey, ...]:
    """The tenant's ACTIVE AWS accounts, in account id order."""
    rows = connection.execute(
        text(ACTIVE),
        {
            "tenant": tenant_id,
            "provider": Provider.AWS.value,
            "status": AccountStatus.ACTIVE.value,
        },
    ).scalars()
    return tuple(AccountKey(provider=Provider.AWS, account_id=account_id) for account_id in rows)
