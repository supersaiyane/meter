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
    """What the provider says about the account, not what we infer.

    The values are the ones `docs/07-DATA-MODEL.md` stores, because a domain
    enum and a database check constraint that disagree fail at the first write
    and not one moment before.

    `UNKNOWN` is for a status the adapter does not recognise. The account is
    still returned, because dropping it shrinks the denominator that
    `scope_coverage` and every organization total are computed from, which is
    ISS-016 arriving by another route. The collector raises SchemaDrift
    alongside it, so the unrecognised value is loud rather than absorbed.
    """

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    PENDING = "PENDING"
    DEPARTED = "DEPARTED"
    UNKNOWN = "UNKNOWN"


class RoleHealth(StrEnum):
    """Whether the collector role in a member account is actually usable.

    `NOT_DEPLOYED` and `ACCESS_DENIED` are kept apart deliberately. The first
    means the StackSet has not reached the account and the fix belongs to
    whoever owns the deployment. The second means the role is there and its
    policy is wrong, and the fix belongs to whoever owns the policy. Collapsing
    them produces a single message that sends half the cases to the wrong person.

    `UNKNOWN` is not a synonym for either. It is the honest answer when the
    provider refused without saying which of the two it was, and the recorded
    error is what a human uses to tell them apart.
    """

    HEALTHY = "HEALTHY"
    ACCESS_DENIED = "ACCESS_DENIED"
    NOT_DEPLOYED = "NOT_DEPLOYED"
    THROTTLED = "THROTTLED"
    UNKNOWN = "UNKNOWN"


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


@dataclass(frozen=True, kw_only=True)
class AccountHealth(Fact):
    """Whether we could actually use the collector role, and why not if not."""

    key: AccountKey
    health: RoleHealth
    #: What the provider said, kept verbatim so a user can act without reading
    #: logs. Empty only when the check succeeded.
    error: str = ""

    @property
    def is_usable(self) -> bool:
        return self.health is RoleHealth.HEALTHY
