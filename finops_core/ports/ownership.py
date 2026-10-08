"""Where an estate names a resource's owners, beyond its tags. FEAT-077, TASK-P11-001.

Two ports, P11 spec sections 5.3 and 5.4, because the service catalogue and the record of who
created a resource are read from different places and fail apart. Tags need no port: they arrive
with the inventory, `ResourceInventory`, and are read from what it stored.

Read only, constraint 6: nothing here tags, catalogues or changes a resource.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from finops_core.domain.account import AccountKey
from finops_core.domain.ownership import BeforeHistory, CatalogueApplication, Creator


@runtime_checkable
class ServiceCatalogue(Protocol):
    """The applications an account declares, who owns each, and the tags that mark its resources."""

    def applications(self, account: AccountKey, region: str) -> Iterable[CatalogueApplication]:
        """Every application in this account and Region.

        An application that names no owner is still returned, with the owner None: the catalogue
        was read, and it says nobody. Its resources are matched by the tags it marks them with.

        Raises:
            AccessDenied: The session may not read the catalogue in this account.
            Throttled: The provider rejected the call rate.
            NotOptedIn: The Region is not enabled for the account.
            Unreachable: The endpoint did not answer.
            SchemaDrift: An application's attributes are not the shape this reads.
        """
        ...


@runtime_checkable
class ResourceCreators(Protocol):
    """Who created a resource, from the provider's record of the event that did."""

    def creator(
        self, account: AccountKey, region: str, resource_id: str
    ) -> Creator | BeforeHistory:
        """The principal that created the resource, or that it predates the record.

        Never a guess: a resource the record does not reach is `BeforeHistory`, with how far back
        the record goes.

        Raises:
            AccessDenied: The session may not read the event record in this account.
            Throttled: The provider rejected the call rate.
            NotOptedIn: The Region is not enabled for the account.
            Unreachable: The endpoint did not answer.
            SchemaDrift: The creating event names its principal in no place this reads.
        """
        ...
