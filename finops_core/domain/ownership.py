"""Who an estate says owns a resource, and how it knows. FEAT-077, TASK-P11-001.

P11 spec sections 5.1 to 5.4. A resource can have an owner a person assigned, FEAT-028, and up to
three suggested ones, each from a source and each a fact with its two timestamps:

1. **The service catalogue**: the application a resource is associated with, and the owner its
   attributes name. Strongest, because somebody wrote it down as ownership.
2. **A tag**: the first of the deployment's owner tag keys the resource carries.
3. **The creator**: the principal of the event that created it. Weakest, because whoever created a
   thing is often not whoever runs it.

A suggestion is never an owner. Nothing here writes one, and nothing reading these should either:
ISS-021's rule is that a wrongly assigned owner is worse than an absent one.

Query findings have their own owner, from Grafana folders and last editors,
`finops_query/ownership.py`, FEAT-016; these are a resource's.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from finops_core.domain.account import AccountKey
from finops_core.domain.fact import Fact


class OwnerSource(StrEnum):
    """Where a suggested owner came from."""

    CATALOGUE = "CATALOGUE"
    TAG = "TAG"
    CREATOR = "CREATOR"


#: Strongest first, spec section 5.1.
ORDER: Final = (OwnerSource.CATALOGUE, OwnerSource.TAG, OwnerSource.CREATOR)


class OwnerKind(StrEnum):
    """What a suggested owner is, which decides whether a person can be asked."""

    TEAM = "TEAM"
    PERSON = "PERSON"
    #: A pipeline's role. Named so it is never mistaken for somebody to ask.
    AUTOMATION = "AUTOMATION"


def _named(value: str, what: str) -> None:
    if not value.strip():
        raise ValueError(f"{what} is blank, and a blank says nothing")


def _in_order(as_of: datetime, collected_at: datetime) -> None:
    if collected_at < as_of:
        raise ValueError(
            "collected_at is earlier than as_of, so the fact was read before it was true"
        )


@dataclass(frozen=True, kw_only=True)
class OwnerSuggestion(Fact):
    """One source's answer to who owns a resource."""

    account_key: AccountKey
    region_id: str
    resource_id: str
    source: OwnerSource
    owner: str
    kind: OwnerKind
    #: Which tag key, which application, or which event: enough to go and check.
    detail: str

    def __post_init__(self) -> None:
        _named(self.resource_id, "resource_id")
        _named(self.owner, "owner")
        _named(self.detail, "detail")
        _in_order(self.as_of, self.collected_at)
        if self.source is OwnerSource.TAG and self.kind is not OwnerKind.TEAM:
            raise ValueError("a tag names a team, never a person or a pipeline")
        if self.source is OwnerSource.CREATOR and self.kind is OwnerKind.TEAM:
            raise ValueError("a creator is a person or a pipeline, never a team")


def strongest_first(suggestions: Iterable[OwnerSuggestion]) -> tuple[OwnerSuggestion, ...]:
    """The suggestions in the order of spec section 5.1, a source's own order kept within it."""
    return tuple(sorted(suggestions, key=lambda one: ORDER.index(one.source)))


@dataclass(frozen=True, kw_only=True)
class CatalogueApplication(Fact):
    """An application the catalogue declares, the owner it names, and how its resources are known.

    A catalogue does not list an application's resources one by one: AWS AppRegistry associates
    stacks and a tag value with an application, TASK-P11-003. So an application carries the tags
    that mark a resource as its own, and a resource is matched by the tags the inventory already
    holds. The tag keys are the provider's, supplied by its adapter, which keeps this provider
    neutral, constraint 1.
    """

    account_key: AccountKey
    region_id: str
    name: str
    application_id: str
    #: None where the application names nobody, which is a fact about the catalogue: it was read,
    #: and it says nobody.
    owner: str | None
    #: The tag key and value pairs that mark a resource as this application's.
    marks: frozenset[tuple[str, str]]

    def __post_init__(self) -> None:
        _named(self.name, "name")
        _named(self.application_id, "application_id")
        if self.owner is not None:
            _named(self.owner, "owner")
        _in_order(self.as_of, self.collected_at)

    def holds(self, tags: Mapping[str, str]) -> bool:
        """Whether a resource with these tags is this application's."""
        return any(tags.get(key) == value for key, value in self.marks)


@dataclass(frozen=True, kw_only=True)
class Creator(Fact):
    """The principal of the event that created a resource."""

    account_key: AccountKey
    region_id: str
    resource_id: str
    #: A person's name, or a pipeline's role, as the event names it.
    principal: str
    kind: OwnerKind
    event_id: str
    #: When the resource was created, which is also `as_of`.
    created_at: datetime

    def __post_init__(self) -> None:
        _named(self.resource_id, "resource_id")
        _named(self.principal, "principal")
        _named(self.event_id, "event_id")
        if self.kind is OwnerKind.TEAM:
            raise ValueError("a creator is a person or a pipeline, never a team")
        _in_order(self.as_of, self.collected_at)


@dataclass(frozen=True, kw_only=True)
class BeforeHistory(Fact):
    """A resource created before the event history begins, so its creator cannot be read.

    Said rather than guessed: the earliest moment the history reaches is kept, so a reader knows
    how far back was searched.
    """

    account_key: AccountKey
    region_id: str
    resource_id: str
    #: The earliest event the history holds; the resource is older.
    history_starts: datetime

    def __post_init__(self) -> None:
        _named(self.resource_id, "resource_id")
        _in_order(self.as_of, self.collected_at)
