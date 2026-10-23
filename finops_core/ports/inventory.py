"""Enumerating resources and the relationships between them.

P0 does not implement this. It is defined now because retrofitting a port once
three consumers have grown around its absence is the expensive version of the
same work.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from finops_core.domain.account import AccountKey
from finops_core.domain.resource import ResourceRef


@runtime_checkable
class ResourceInventory(Protocol):
    """Reads what exists in an account, and what depends on what."""

    def list_resources(
        self, account: AccountKey, region: str, resource_type: str | None = None
    ) -> Iterable[ResourceRef]:
        """Every resource in the account and region, optionally of one type.

        Raises:
            AccessDenied: The session may not read the inventory in this account.
            NotOptedIn: The inventory service has never been enabled here.
            NoData: The account and region hold nothing of this type.
            Throttled: The provider rejected the call rate.
            Unreachable: The inventory endpoint did not answer.
        """
        ...

    def list_dependencies(self, account: AccountKey, resource_id: str) -> Iterable[ResourceRef]:
        """What the named resource depends on, one level out.

        The graph is walked by the caller rather than here, because a walk that
        happens inside an adapter is a walk nobody can bound.

        Raises:
            AccessDenied: The session may not read the inventory in this account.
            NoData: The resource exists and depends on nothing.
            Throttled: The provider rejected the call rate.
            Unreachable: The inventory endpoint did not answer.
            SchemaDrift: A relationship arrived in a shape this adapter does not
                recognise.
        """
        ...
