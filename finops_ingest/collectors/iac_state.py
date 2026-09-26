"""Which infrastructure as code address owns each resource.

FEAT-057, TASK-P4-013. The rule is in `finops_core/domain/iac.py` and is pure; this module
reads the configured state, resolves each resource to an account, and writes the ones it found.

**It writes presence and never absence.** A row means we found a resource in state. No row
means we did not find it, which is a different fact from nobody managing it, and the entity page
derives the difference at read time from a declaration about our own configuration. Writing
`UNMANAGED` here would freeze a judgement made under today's configuration into a row that
outlives it, and somebody would act on it after a workspace was added.

**It resolves each resource to an account before writing, and counts the ones it cannot.** A
state file routinely owns resources Meter has never inventoried, and there is no account column
in a state file: the account comes from the node the ARN joined to. A managed resource with no
node is therefore not an error, it is evidence about our inventory, and the count is reported on
`sync_error` for the same reason `unmatched_findings` is on the entity page. Parsing the account
out of the ARN instead would have written rows for resources we know nothing else about, keyed
by a string that looked like an account.

**Nothing is retracted for a location that refused us.** A resource whose state location was
unreadable this morning keeps yesterday's row rather than losing it, because a removed row reads
as "not determined" and that would report a managed resource as unknown on the strength of a
failure. Removal happens only for locations that were read: the same rule the inventory
collector follows with `CoverageState.COMPLETE`, applied per state location instead of per slice.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from finops_core.domain.iac import StateRead
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "iac_state"
SCOPE = "iac"

#: Upserted on the resource. A resource moved between state files gets its row updated rather
#: than gaining a second, because two addresses for one resource would let FEAT-040 open a pull
#: request against whichever the query happened to return first.
WRITE = text(
    "INSERT INTO resource_management (management_id, tenant_id, ingest_run_id, "
    "sub_account_id, provider_id, address, state_reference, as_of, collected_at) "
    "VALUES (:id, :tenant, :run, :account, :provider_id, :address, :reference, :at, :at) "
    "ON CONFLICT (tenant_id, provider_id) DO UPDATE SET "
    "ingest_run_id = EXCLUDED.ingest_run_id, sub_account_id = EXCLUDED.sub_account_id, "
    "address = EXCLUDED.address, state_reference = EXCLUDED.state_reference, "
    "as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at"
)

#: Where a resource lives, from the inventory rather than from the ARN. One statement for the
#: whole batch, because a per resource lookup over a real state file is thousands of queries.
ACCOUNTS_FOR = text(
    "SELECT provider_id, sub_account_id FROM topology_node "
    "WHERE tenant_id = :tenant AND provider_id = ANY(:ids)"
)

#: Rows for locations this run did read and no longer found there. Limited to those locations
#: on purpose: one that refused us keeps its rows, because removing them would report a managed
#: resource as not determined on the strength of a failure, which is the inverse of the mistake
#: this feature exists to prevent.
RETRACT = text(
    "DELETE FROM resource_management "
    "WHERE tenant_id = :tenant AND state_reference = ANY(:locations) "
    "AND ingest_run_id <> :run"
)

#: Recorded rather than silent, like every other collector's shortfall.
REFUSED = text(
    "INSERT INTO sync_error (error_id, tenant_id, collector, scope_key, error_type, "
    "detail, remediation, first_seen_at, last_seen_at, occurrences) "
    "VALUES (:id, :t, :c, :s, :type, :d, :r, :now, :now, 1) "
    "ON CONFLICT (tenant_id, collector, scope_key, error_type) DO UPDATE SET "
    "detail = EXCLUDED.detail, last_seen_at = EXCLUDED.last_seen_at, "
    "occurrences = sync_error.occurrences + 1"
)


def _system_clock() -> datetime:
    return datetime.now(UTC)


Clock = Callable[[], datetime]


class IacStateCollector:
    """The addresses that own our resources, from the state an operator configured."""

    def __init__(self, source: Any, clock: Clock = _system_clock) -> None:
        self._source = source
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        settings = context.settings
        if settings is None:
            raise ValueError(
                "iac_state needs settings. Its state locations are configuration, and "
                "searching for them instead would mean listing somebody's buckets."
            )

        now = self._clock()
        locations = settings.iac_locations
        if not locations:
            # A real deployment, not a failure. Nothing is configured, so nothing is read and
            # every resource reads as not determined, which is true. Returning zero rather than
            # raising is what lets the collector be scheduled before anybody configures it.
            return CollectorOutcome(items_written=0)

        read: StateRead = self._source.read(locations)
        for location, cause in read.refused:
            context.connection.execute(
                REFUSED,
                {
                    "id": uuid4(),
                    "t": context.unit.tenant_id,
                    "c": COLLECTOR,
                    "s": location,
                    "type": cause,
                    "d": f"{location} could not be read, so what it manages is not known",
                    "r": (
                        "Check the hub role may read this object. Until it can, resources in "
                        "it read as not determined rather than as unmanaged, and Meter will "
                        "not say any account is wholly unmanaged."
                    ),
                    "now": now,
                },
            )

        placed = self._accounts_for(context, [one.provider_id for one in read.managed])
        written = 0
        unplaceable = 0
        for resource in read.managed:
            account = placed.get(resource.provider_id)
            if account is None:
                # Terraform owns something Meter has never inventoried. Counted, because a
                # state file full of resources we cannot join is a fact about our inventory.
                unplaceable += 1
                continue
            context.connection.execute(
                WRITE,
                {
                    "id": uuid4(),
                    "tenant": context.unit.tenant_id,
                    "run": context.run_id,
                    "account": account,
                    "provider_id": resource.provider_id,
                    "address": resource.address,
                    "reference": resource.state_reference,
                    "at": now,
                },
            )
            written += 1

        # Only the locations that were read. A refused location keeps its rows.
        refused_at = {location for location, _cause in read.refused}
        was_read = [one for one in locations if one not in refused_at]
        if was_read:
            context.connection.execute(
                RETRACT,
                {
                    "tenant": context.unit.tenant_id,
                    "locations": was_read,
                    "run": context.run_id,
                },
            )

        if unplaceable:
            context.connection.execute(
                REFUSED,
                {
                    "id": uuid4(),
                    "t": context.unit.tenant_id,
                    "c": COLLECTOR,
                    "s": SCOPE,
                    "type": "NoData",
                    "d": (
                        f"{unplaceable} resources in state matched no inventoried resource, so "
                        "nothing records what manages them"
                    ),
                    "r": (
                        "Usually the inventory has not reached those accounts yet, or the "
                        "resource type has no ARN and cannot be joined. Neither is a state "
                        "problem, and neither means the resources are unmanaged."
                    ),
                    "now": now,
                },
            )

        return CollectorOutcome(items_written=written)

    def _accounts_for(self, context: CollectorContext, ids: list[str]) -> dict[str, str]:
        """Where each resource lives, from the inventory.

        One statement for the batch. A per resource lookup over a real state file is thousands
        of queries against a table whose only job here is to answer which account.
        """
        if not ids:
            return {}
        rows = context.connection.execute(
            ACCOUNTS_FOR, {"tenant": context.unit.tenant_id, "ids": ids}
        ).all()
        return {str(row.provider_id): str(row.sub_account_id) for row in rows}
