"""Getting an authenticated handle for one account, without naming a provider.

ADR-0004. The hub assumes a role the member account trusts, which means the
failure modes here are the ones every other port inherits: the role may not
exist, the trust policy may not admit us, and the provider may throttle the
assume call itself.

`ProviderSession` is opaque on purpose. It exposes when it expires and nothing
else. An adapter knows what is behind it; the domain never needs to, and the
moment the domain can reach a client object, `finops_core` has a cloud SDK in
its import graph again.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from finops_core.domain.account import AccountKey


@runtime_checkable
class ProviderSession(Protocol):
    """An authenticated handle for one account and one region. Opaque by design."""

    @property
    def expires_at(self) -> datetime:
        """When this handle stops working, so a long run can renew before it does."""
        ...


@runtime_checkable
class CredentialBroker(Protocol):
    """Produces a scoped session for a target account."""

    def session_for(self, account: AccountKey, region: str) -> ProviderSession:
        """Assume into `account` in `region` and return a session.

        Raises:
            AccessDenied: The role is absent, or its trust policy does not admit
                the hub. This is the expected failure for an account that was
                never enrolled, and it is never a reason to report zero.
            Throttled: The provider rejected the rate of assume calls.
            Unreachable: The identity endpoint did not answer.
        """
        ...
