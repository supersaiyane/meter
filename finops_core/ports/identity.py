"""Who the caller is, and what they may read.

ADR-0008 defers the identity provider decision, which is only affordable
because both halves sit behind these two ports. Nothing above this line knows
whether the answer came from a local file or from an enterprise directory.

Constraint 3 puts scope enforcement in two independent places. This port
supplies the scope; it does not enforce it.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from finops_core.domain.identity import Entitlement, Principal


@runtime_checkable
class IdentityProvider(Protocol):
    """Turns a credential presented by a caller into a principal."""

    def authenticate(self, token: str) -> Principal:
        """The principal the token identifies.

        Raises:
            AccessDenied: The token is absent, expired, or not one we issued.
                Never distinguish the three to the caller.
            Unreachable: The directory did not answer.
            SchemaDrift: The directory returned a principal without the claims
                this adapter requires.
        """
        ...


@runtime_checkable
class EntitlementResolver(Protocol):
    """Turns a principal into the scope it may read."""

    def resolve(self, principal: Principal) -> Entitlement:
        """The entitlement held by the principal, carrying its own `as_of`.

        An unknown principal resolves to an empty scope rather than raising,
        because an empty scope fails closed and an exception here tempts a
        caller into a fallback that does not.

        Raises:
            AccessDenied: The directory refused the group lookup.
            Unreachable: The directory did not answer.
            SchemaDrift: A group mapping arrived in a shape this adapter does
                not recognise.
        """
        ...
