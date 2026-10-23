"""A reference to one resource, with no provider identifier in it.

The identifier is opaque text and the type is the provider's own word for it.
Neither is parsed here. Reading structure out of a provider identifier is how
an adapter's format becomes a domain assumption.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from finops_core.domain.account import AccountKey
from finops_core.domain.fact import Fact


@dataclass(frozen=True, kw_only=True)
class ResourceRef(Fact):
    """One resource as the provider described it at `as_of`."""

    account_key: AccountKey
    resource_id: str
    resource_type: str
    region_id: str | None
    name: str | None
    tags: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tags", MappingProxyType(dict(self.tags)))
