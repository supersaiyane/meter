"""Owners for the fake estate beyond its tags. TASK-P11-001, P11 spec section 9.

Planted where the estate needs them most, in `fake-product-b`, the account whose resources carry
no team tag, the same hole the bill has:

- **The service catalogue** names `payments` for the oversized instance `fake-product-b/0004`, in
  the application `checkout`; the application `reporting` names nobody and holds the account's
  database, so a catalogue that was read and says nobody is a case too.
- **CloudTrail's record** names a person for `fake-product-b/0003`, created nine days before the
  estate's clock as its launch says, and the role `deploy-pipeline`, a pipeline and never a person,
  for the account's NAT gateway, re-created thirty days before.
- **Everything else predates the record's 90 days**, `fake-product-b/0002` among them, launched
  240 days before, and says so rather than naming anybody.

The fourth case, an owner under a second tag key, is in the estate itself:
`amazonebs/fake-product-b/0001` carries `owner: data-platform` and no `team`, `utilization.py`.

The names are invented, under `fake.example`, a domain nobody can receive mail at.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import timedelta
from typing import Final

from finops_core.domain.account import AccountKey
from finops_core.domain.ownership import BeforeHistory, CatalogueEntry, Creator, OwnerKind
from finops_core.errors import CollectionError
from finops_fakes import fixtures

COLLECTOR: Final = "ownership"
#: How far back CloudTrail's event history reaches, as AWS documents it.
HISTORY_DAYS: Final = 90

#: Account, Region, resource, application, and the owner it names or None.
CATALOGUE: Final[tuple[tuple[str, str, str, str, str | None], ...]] = (
    ("fake-product-b", "us-fake-1", "amazonec2/fake-product-b/0004", "checkout", "payments"),
    ("fake-product-b", "us-fake-1", "amazonrds/fake-product-b/0001", "reporting", None),
)

#: Resource, the principal that created it, what it is, and how many days before the clock.
CREATED: Final[dict[str, tuple[str, OwnerKind, int]]] = {
    "amazonec2/fake-product-b/0003": ("dev.lead@fake.example", OwnerKind.PERSON, 9),
    "amazonvpc/fake-product-b/nat-0001": ("deploy-pipeline", OwnerKind.AUTOMATION, 30),
}


def _event_id(resource_id: str) -> str:
    """An event id in CloudTrail's form, the same every time for one resource."""
    digest = hashlib.sha256(resource_id.encode()).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


class _Failing:
    def __init__(self, failure: type[CollectionError] | None, accounts: frozenset[str]) -> None:
        self._failure = failure
        self._accounts = accounts

    def _fail(self, account: AccountKey) -> None:
        # Every account when none is named, else only those, so one account failing can be
        # shown leaving the others standing.
        if self._failure is not None and (
            not self._accounts or account.account_id in self._accounts
        ):
            raise self._failure(
                scope_key=account.account_id,
                collector=COLLECTOR,
                detail="planned by the fake ownership source",
            )


class FakeServiceCatalogue(_Failing):
    """AppRegistry's applications in the fake estate."""

    def __init__(
        self,
        *,
        failure: type[CollectionError] | None = None,
        accounts: Iterable[str] = (),
    ) -> None:
        super().__init__(failure, frozenset(accounts))

    def entries(self, account: AccountKey, region: str) -> Iterable[CatalogueEntry]:
        self._fail(account)
        return tuple(
            CatalogueEntry(
                account_key=account,
                region_id=region,
                resource_id=resource,
                application=application,
                owner=owner,
                as_of=fixtures.AS_OF,
                collected_at=fixtures.COLLECTED_AT,
            )
            for held, where, resource, application, owner in CATALOGUE
            if held == account.account_id and where == region
        )


class FakeResourceCreators(_Failing):
    """CloudTrail's event history in the fake estate: 90 days, and two creations in it."""

    def __init__(
        self,
        *,
        failure: type[CollectionError] | None = None,
        accounts: Iterable[str] = (),
    ) -> None:
        super().__init__(failure, frozenset(accounts))

    def creator(
        self, account: AccountKey, region: str, resource_id: str
    ) -> Creator | BeforeHistory:
        self._fail(account)
        found = CREATED.get(resource_id)
        if found is None:
            return BeforeHistory(
                account_key=account,
                region_id=region,
                resource_id=resource_id,
                history_starts=fixtures.AS_OF - timedelta(days=HISTORY_DAYS),
                as_of=fixtures.AS_OF,
                collected_at=fixtures.COLLECTED_AT,
            )
        principal, kind, days = found
        created = fixtures.AS_OF - timedelta(days=days)
        return Creator(
            account_key=account,
            region_id=region,
            resource_id=resource_id,
            principal=principal,
            kind=kind,
            event_id=_event_id(resource_id),
            created_at=created,
            as_of=created,
            collected_at=fixtures.COLLECTED_AT,
        )
