"""Enumerating resources and the relationships between them.

Two ports. `ResourceInventory` was defined in P0 and nothing implements it: it is
here because retrofitting a port once three consumers have grown around its
absence is the expensive version of the same work.

`TopologySource` is P4's, and it is a different shape rather than an extension of
the first for one reason. `list_resources` raises on failure, which is right for a
caller reading one account: the answer is unknown and unknown is not zero.
`read_slice` cannot raise, because the thing it is reporting on is a partial
success, and an exception carries exactly one cause while a slice can fall short in
four ways at once and still be worth writing down. Section 6 of the P4
specification: an edge Meter cannot see is not an absent edge, and an exception
would leave the caller with no edges and no record of which API refused.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from finops_core.domain.account import AccountKey
from finops_core.domain.resource import ResourceRef
from finops_core.domain.topology import SliceRead


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


@runtime_checkable
class TopologySource(Protocol):
    """Reads one account and one region of the graph, and says what it missed."""

    def read_slice(self, account: AccountKey, region: str | None) -> SliceRead:
        """Every node and edge this source can see in the slice, plus shortfalls.

        A region of None is the account's global slice, where an IAM role and the
        TRUSTS edges between roles live.

        **This does not raise a `CollectionError`.** Every failure that is about one
        API rather than about the whole call arrives as a `Shortfall` in the result,
        because a slice where three of four APIs answered is a slice worth writing
        and an exception would discard all three. The caller turns an empty
        `shortfalls` into a COMPLETE coverage row and a non empty one into PARTIAL.

        It may still raise for a failure that is not about the estate at all: a
        malformed argument, or a credential the broker could not assume, where there
        is nothing partial to report and no slice was read.
        """
        ...

    @property
    def enrolled_slices(self) -> tuple[tuple[AccountKey, str | None], ...]:
        """Every slice this source is expected to be able to read.

        The denominator. TASK-P4-005 requires an UNREAD row at enrolment rather than
        at first failure, and a row can only be written for a slice something has
        named. Without this the set of slices would be inferred from the slices that
        were successfully read, which is the circular definition that makes an
        unread region indistinguishable from one that does not exist.
        """
        ...
