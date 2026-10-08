"""Who an estate says owns each resource, read into `resource_owner`. FEAT-077, TASK-P11-002.

P11 spec sections 5.1 to 5.4 and 7. Daily. Each source's answer is checked against the rules of
`OwnerSuggestion` before it is written, so a row this writes is one the domain would accept.

**Tags need no AWS call.** The inventory already holds each resource's tags, `topology_node`, and
the first of the deployment's `owner_tag_keys` a resource carries with a value names its team.
The keys are configuration, not constants: a deployment whose owners live under `owner` or
`cost-center` says so, and without settings the collector refuses rather than guessing them.

**The catalogue marks its resources by tags too**, TASK-P11-003. AWS AppRegistry associates
stacks and a tag value with an application rather than listing its resources, so each application
comes with the tags that mark its resources and a node is matched by the tags it carries. Only an
application that names an owner suggests one; an owner with an `@` in it is a person, any other a
team. A catalogue refused in one account and Region is typed in `sync_error`, its rows there are
kept rather than read as nobody, and every other account and Region still loads.

**Creators are asked once**, TASK-P11-004. A resource neither a tag nor the catalogue names is
asked of CloudTrail's event history, at most `creator_lookups_per_run` a run, and the answer is
kept in `creator_lookup`: the creator found, written as a CREATOR row, or a resource older than the
history, said with where the history began. Either way it is never asked again, because who
created a resource does not change. A refusal is typed in `sync_error`, the rest of that account
and Region waits for the next run, and nothing is recorded as asked.

**Replaced, not accumulated.** A run writes what tags and the catalogue said, and removes that
source's rows it did not find again, so a tag taken off a resource stops suggesting its team. A
source the run did not read keeps its rows, and a creator's row is kept, since it cannot change.

**Never an owner.** Nothing here writes `recommendation.owner`. A suggestion is a person's to
accept, ISS-021.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.ownership import (
    BeforeHistory,
    CatalogueApplication,
    Creator,
    OwnerKind,
    OwnerSource,
    OwnerSuggestion,
)
from finops_core.errors import CollectionError
from finops_core.ports.ownership import ResourceCreators, ServiceCatalogue
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "ownership"

#: Every resource the inventory holds, with its tags.
NODES = text(
    "SELECT sub_account_id, region_id, provider_id, tags, as_of FROM topology_node "
    "WHERE tenant_id = :t"
)

UPSERT = text(
    "INSERT INTO resource_owner (owner_pk, tenant_id, ingest_run_id, sub_account_id, region_id, "
    "resource_id, source, owner, owner_kind, detail, as_of, collected_at) VALUES (:pk, :t, :run, "
    ":account, :region, :resource, :source, :owner, :kind, :detail, :as_of, :now) "
    "ON CONFLICT (tenant_id, sub_account_id, resource_id, source) DO UPDATE SET "
    "ingest_run_id = EXCLUDED.ingest_run_id, region_id = EXCLUDED.region_id, "
    "owner = EXCLUDED.owner, owner_kind = EXCLUDED.owner_kind, detail = EXCLUDED.detail, "
    "as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at"
)

#: One source's rows this run did not find again.
WITHDRAW = text(
    "DELETE FROM resource_owner WHERE tenant_id = :t AND source = :source AND ingest_run_id <> :run"
)

#: The same, sparing the accounts and Regions whose source could not be read this run, so a
#: refusal keeps what was known rather than reading as nobody owning anything.
WITHDRAW_READ = text(
    "DELETE FROM resource_owner WHERE tenant_id = :t AND source = :source "
    "AND ingest_run_id <> :run "
    "AND NOT (sub_account_id || ':' || coalesce(region_id, '')) = ANY(:refused)"
)

#: The resources CloudTrail has not been asked about and no tag or catalogue names, a run's worth.
#: A resource no Region holds is not asked: the event history is kept Region by Region.
UNASKED = text(
    "SELECT n.sub_account_id, n.region_id, n.provider_id FROM topology_node n "
    "WHERE n.tenant_id = :t AND n.region_id IS NOT NULL "
    "AND NOT EXISTS (SELECT 1 FROM creator_lookup l WHERE l.tenant_id = n.tenant_id "
    "AND l.sub_account_id = n.sub_account_id AND l.resource_id = n.provider_id) "
    "AND NOT EXISTS (SELECT 1 FROM resource_owner o WHERE o.tenant_id = n.tenant_id "
    "AND o.sub_account_id = n.sub_account_id AND o.resource_id = n.provider_id "
    "AND o.source <> 'CREATOR') "
    "ORDER BY n.sub_account_id, n.region_id, n.provider_id LIMIT :cap"
)

#: A resource asked about, so it is never asked again.
ASKED = text(
    "INSERT INTO creator_lookup (lookup_pk, tenant_id, ingest_run_id, sub_account_id, region_id, "
    "resource_id, outcome, history_starts, as_of, collected_at) VALUES (:pk, :t, :run, "
    ":account, :region, :resource, :outcome, :starts, :as_of, :now) "
    "ON CONFLICT (tenant_id, sub_account_id, resource_id) DO NOTHING"
)

#: Upserted on the scope, like every other sync error.
REFUSED = text(
    "INSERT INTO sync_error (error_id, tenant_id, collector, scope_key, error_type, "
    "detail, remediation, first_seen_at, last_seen_at, occurrences) "
    "VALUES (:id, :t, :c, :s, :type, :d, :r, :now, :now, 1) "
    "ON CONFLICT (tenant_id, collector, scope_key, error_type) DO UPDATE SET "
    "detail = EXCLUDED.detail, last_seen_at = EXCLUDED.last_seen_at, "
    "occurrences = sync_error.occurrences + 1"
)

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


def team_of(tags: Mapping[str, Any], keys: Sequence[str]) -> tuple[str, str] | None:
    """The first owner tag key a resource carries with a value, and that value, or None."""
    for key in keys:
        value = tags.get(key)
        if isinstance(value, str) and value.strip():
            return key, value.strip()
    return None


class OwnershipCollector:
    """Every resource's suggested owners, from each source it is given."""

    def __init__(
        self,
        *,
        clock: Clock = _system_clock,
        catalogue: ServiceCatalogue | None = None,
        creators: ResourceCreators | None = None,
    ) -> None:
        self._clock = clock
        # None where the deployment reads no catalogue, and then its rows are left alone.
        self._catalogue = catalogue
        # None where the deployment reads no event history, and then nothing is asked.
        self._creators = creators

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        if context.settings is None:
            raise ValueError(
                "ownership needs settings. The owner tag keys are configuration, and guessing "
                "them would name a team nobody chose."
            )
        now = self._clock()
        tenant = context.unit.tenant_id
        keys = context.settings.owner_tag_key_list
        nodes = list(context.connection.execute(NODES, {"t": tenant}))
        found = [
            suggestion for node in nodes if (suggestion := _from_tags(node, keys, now)) is not None
        ]
        if found:
            context.connection.execute(UPSERT, [_row(context, one, now) for one in found])
        removed = context.connection.execute(
            WITHDRAW, {"t": tenant, "source": OwnerSource.TAG.value, "run": context.run_id}
        ).rowcount
        written = len(found)
        if self._catalogue is not None:
            catalogued, withdrawn = self._from_catalogue(context, self._catalogue, nodes, now)
            written += catalogued
            removed += withdrawn
        if self._creators is not None:
            # Last, so a resource this run's tags or catalogue just named is not asked about.
            written += self._from_creators(
                context, self._creators, context.settings.creator_lookups_per_run, now
            )
        return CollectorOutcome(items_written=written, items_removed=removed)

    def _from_creators(
        self, context: CollectorContext, creators: ResourceCreators, cap: int, now: datetime
    ) -> int:
        """Each unasked resource's creator, or that it is older than the history; how many."""
        unasked = context.connection.execute(UNASKED, {"t": context.unit.tenant_id, "cap": cap})
        refused: set[tuple[str, str]] = set()
        answers: list[Creator | BeforeHistory] = []
        for node in list(unasked):
            where = (node.sub_account_id, node.region_id)
            if where in refused:
                continue
            account = AccountKey(provider=Provider.AWS, account_id=node.sub_account_id)
            try:
                answers.append(creators.creator(account, node.region_id, node.provider_id))
            except CollectionError as failure:
                _record(context, failure, now)
                refused.add(where)
        found = [_from_creator(one, now) for one in answers if isinstance(one, Creator)]
        if found:
            context.connection.execute(UPSERT, [_row(context, one, now) for one in found])
        if answers:
            context.connection.execute(ASKED, [_asked(context, one, now) for one in answers])
        return len(answers)

    def _from_catalogue(
        self,
        context: CollectorContext,
        catalogue: ServiceCatalogue,
        nodes: Sequence[Any],
        now: datetime,
    ) -> tuple[int, int]:
        """Each node an application with an owner marks, one account and Region at a time."""
        found: list[OwnerSuggestion] = []
        refused: list[str] = []
        for account_id, region in sorted(
            {(n.sub_account_id, n.region_id) for n in nodes if n.region_id}
        ):
            account = AccountKey(provider=Provider.AWS, account_id=account_id)
            try:
                applications = sorted(
                    catalogue.applications(account, region), key=lambda one: one.name
                )
            except CollectionError as failure:
                _record(context, failure, now)
                refused.append(f"{account_id}:{region}")
                continue
            here = (n for n in nodes if (n.sub_account_id, n.region_id) == (account_id, region))
            found.extend(
                suggestion
                for node in here
                if (suggestion := _from_catalogue(node, applications, now)) is not None
            )
        if found:
            context.connection.execute(UPSERT, [_row(context, one, now) for one in found])
        withdrawn = context.connection.execute(
            WITHDRAW_READ,
            {
                "t": context.unit.tenant_id,
                "source": OwnerSource.CATALOGUE.value,
                "run": context.run_id,
                "refused": refused,
            },
        ).rowcount
        return len(found), withdrawn


def _from_tags(node: Any, keys: Sequence[str], now: datetime) -> OwnerSuggestion | None:
    named = team_of(node.tags or {}, keys)
    if named is None:
        return None
    key, team = named
    return OwnerSuggestion(
        account_key=AccountKey(provider=Provider.AWS, account_id=node.sub_account_id),
        region_id=node.region_id or "",
        resource_id=node.provider_id,
        source=OwnerSource.TAG,
        owner=team,
        kind=OwnerKind.TEAM,
        detail=key,
        as_of=node.as_of,
        # A clock behind the inventory's would otherwise record a tag read before it was true.
        collected_at=max(now, node.as_of),
    )


def _from_catalogue(
    node: Any, applications: Sequence[CatalogueApplication], now: datetime
) -> OwnerSuggestion | None:
    tags = node.tags or {}
    holding = next((one for one in applications if one.owner and one.holds(tags)), None)
    if holding is None or holding.owner is None:
        return None
    return OwnerSuggestion(
        account_key=holding.account_key,
        region_id=node.region_id,
        resource_id=node.provider_id,
        source=OwnerSource.CATALOGUE,
        owner=holding.owner,
        # A catalogue owner is whatever somebody wrote: an address names a person.
        kind=OwnerKind.PERSON if "@" in holding.owner else OwnerKind.TEAM,
        detail=holding.name,
        as_of=holding.as_of,
        collected_at=max(now, holding.as_of),
    )


def _from_creator(found: Creator, now: datetime) -> OwnerSuggestion:
    return OwnerSuggestion(
        account_key=found.account_key,
        region_id=found.region_id,
        resource_id=found.resource_id,
        source=OwnerSource.CREATOR,
        owner=found.principal,
        kind=found.kind,
        # The event a reader can open in CloudTrail to check it.
        detail=found.event_id,
        as_of=found.as_of,
        collected_at=max(now, found.as_of),
    )


def _asked(
    context: CollectorContext, answer: Creator | BeforeHistory, now: datetime
) -> dict[str, Any]:
    starts = answer.history_starts if isinstance(answer, BeforeHistory) else None
    return {
        "pk": uuid4(),
        "t": context.unit.tenant_id,
        "run": context.run_id,
        "account": answer.account_key.account_id,
        "region": answer.region_id,
        "resource": answer.resource_id,
        "outcome": "FOUND" if starts is None else "BEFORE_HISTORY",
        "starts": starts,
        "as_of": answer.as_of,
        "now": max(now, answer.as_of),
    }


def _record(context: CollectorContext, failure: CollectionError, now: datetime) -> None:
    context.connection.execute(
        REFUSED,
        {
            "id": uuid4(),
            "t": context.unit.tenant_id,
            "c": COLLECTOR,
            "s": failure.scope_key,
            "type": failure.cause,
            "d": str(failure),
            "r": failure.remediation,
            "now": now,
        },
    )


def _row(context: CollectorContext, one: OwnerSuggestion, now: datetime) -> dict[str, Any]:
    return {
        "pk": uuid4(),
        "t": context.unit.tenant_id,
        "run": context.run_id,
        "account": one.account_key.account_id,
        # A resource no Region holds keeps a null Region, as its node does.
        "region": one.region_id or None,
        "resource": one.resource_id,
        "source": one.source.value,
        "owner": one.owner,
        "kind": one.kind.value,
        "detail": one.detail,
        "as_of": one.as_of,
        "now": max(now, one.as_of),
    }
