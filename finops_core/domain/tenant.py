"""The tenant, and the scope that decides what a request is allowed to read.

Constraint 3 in CLAUDE.md puts scope enforcement in two independent places, a
request dependency and a repository guard. Both of them ask a `Scope` the same
question, so the shape of `Scope` is the shape of the whole rule.

There is no wildcard. A scope is either global, which is a boolean that has to
be granted deliberately, or an explicit set of account keys. The moment a
wildcard string exists, some code path builds one by accident out of an empty
filter, and an empty filter that means everything is how a tenant reads another
tenant's bill. An empty set here means nothing, which fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from finops_core.domain.account import AccountKey


@dataclass(frozen=True, kw_only=True)
class Tenant:
    tenant_id: UUID
    name: str


@dataclass(frozen=True, kw_only=True)
class Scope:
    """What one principal may read, held as data rather than as a query fragment."""

    tenant_id: UUID
    #: Granted deliberately. Never inferred from an absent filter.
    is_global: bool
    #: Explicit membership. Empty means nothing, not everything.
    accounts: frozenset[AccountKey]
    #: Who the scope was resolved for, stamped by the request dependency. Only a row that
    #: belongs to a person reads it, ADR-0029, and None there reads nothing.
    principal_id: str | None = None

    def __post_init__(self) -> None:
        if self.is_global and self.accounts:
            raise ValueError(
                "A global scope must not also enumerate accounts. Two answers to the "
                "same question is how one of them is later read by mistake."
            )

    def permits(self, key: AccountKey) -> bool:
        return self.is_global or key in self.accounts
