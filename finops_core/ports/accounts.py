"""Enumerating accounts and the organization tree.

Nothing returned here is provider shaped. A `CloudAccount` carries an
`AccountKey`, and an `OrgNode` carries a node identifier that is opaque text.
If this port ever returns something with an ARN in it, the abstraction has
already failed and GCP has become a rewrite.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from finops_core.domain.account import CloudAccount
from finops_core.domain.org import OrgNode


@runtime_checkable
class AccountDiscovery(Protocol):
    """Reads which accounts exist and how they are arranged."""

    def list_accounts(self) -> Iterable[CloudAccount]:
        """Every account this organization contains.

        Raises:
            AccessDenied: The organization reader role is missing or not trusted.
            NotOptedIn: The organization service is not enabled for this payer.
            Throttled: The provider rejected the call rate.
            Unreachable: The organization endpoint did not answer.
            SchemaDrift: The response held a field or a status this adapter does
                not recognise, which is loud on purpose.
        """
        ...

    def describe_organization(self) -> Iterable[OrgNode]:
        """Every node of the organization tree, roots and units included.

        Raises:
            AccessDenied: The organization reader role is missing or not trusted.
            NotOptedIn: Trusted access between the organization and the
                deployment service has never been enabled.
            Throttled: The provider rejected the call rate.
            Unreachable: The organization endpoint did not answer.
            SchemaDrift: A node type arrived that is not ROOT, OU or ACCOUNT.
        """
        ...
