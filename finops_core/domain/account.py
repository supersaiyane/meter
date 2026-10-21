"""Accounts, and the key that identifies one without assuming a provider.

An account is identified by the pair `(provider, account_id)` and never by a
bare identifier. A bare twelve digit string in the domain reads as an AWS
account to every future author, and once three call sites assume that, adding
GCP stops being a connector and becomes a rewrite. That is the failure
constraint 1 in CLAUDE.md exists to prevent, expressed as a type.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from finops_core.domain.fact import Fact


class Provider(StrEnum):
    """The clouds this project can name. Only AWS is implemented in P0."""

    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"


class AccountStatus(StrEnum):
    """What the provider says about the account, not what we infer."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, order=True)
class AccountKey:
    """The only way an account is referred to anywhere in the domain."""

    provider: Provider
    account_id: str

    def __str__(self) -> str:
        return f"{self.provider.value}:{self.account_id}"


@dataclass(frozen=True, kw_only=True)
class CloudAccount(Fact):
    """One account, as the provider described it at `as_of`."""

    key: AccountKey
    name: str
    status: AccountStatus
    #: The organization node this account hangs from, if the provider has one.
    parent_node_id: str | None

    @property
    def provider(self) -> Provider:
        return self.key.provider
