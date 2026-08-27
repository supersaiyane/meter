"""Retention as five jobs, not as a policy nobody runs.

Each job is a collector, which is the point rather than a convenience. It claims
a run, records what it changed, and advances a watermark, so a retention job
that silently stops appears on the freshness screen exactly like a collector
that stopped. A policy enforced by something invisible is a policy nobody finds
out has lapsed.

`retention_principal` anonymises and never removes. The row has to survive so
that audit joins do not dangle: `audit_event` stores a principal identifier and
nothing else, and breaking that join is precisely how the audit trail keeps
working while the identification stops. Deleting the row would leave audit
records pointing at nothing.

`retention_cost` aggregates before it drops. Dropping three years of line items
without keeping the monthly shape would destroy the year on year comparison the
retention window was chosen to preserve.

`audit_event` is never touched by an erasure, only by its own retention window.
Removing the record of who read an organization's financial data, at the request
of the person who read it, is not defensible in a financial services
environment. See docs/09-DATA-CLASSIFICATION.md.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy import column, table, text

from finops_ingest.collectors.partitions import (
    PARTITIONED_TABLES,
    detach_partitions_before,
    month_floor,
    partition_maintenance,
)
from finops_ingest.registry import (
    Collector,
    CollectorContext,
    CollectorOutcome,
    CollectorScope,
)

Clock = Callable[[], datetime]

#: What a tombstoned name and address are replaced with. A fixed value rather
#: than a random one, so a reader can tell at a glance that a row was retired by
#: policy and not corrupted.
TOMBSTONE = "anonymised"

_PRINCIPAL_SCOPE = table("principal_scope", column("tenant_id"), column("expires_at"))
_INGEST_RUN = table("ingest_run", column("tenant_id"), column("started_at"))
_SYNC_ERROR = table("sync_error", column("tenant_id"), column("last_seen_at"))
_WATERMARK = table("ingest_watermark", column("tenant_id"), column("updated_at"))
_AUDIT_EVENT = table("audit_event", column("tenant_id"), column("occurred_at"))


def _system_clock() -> datetime:
    return datetime.now(UTC)


def hashed_subject(subject: str) -> str:
    """A stable, non reversible stand in, so a duplicate sign in is still one row."""
    return sha256(subject.encode()).hexdigest()


def _cutoff(clock: Clock, days: int) -> datetime:
    return clock() - timedelta(days=days)


def retention_principal(
    context: CollectorContext, clock: Clock = _system_clock
) -> CollectorOutcome:
    """Anonymise principals unseen past the window. Never removes a row."""
    settings = context.settings
    result = context.connection.execute(
        text(
            "UPDATE principal SET display_name = :tombstone, email = NULL, "
            "subject = :prefix || encode(sha256(subject::bytea), 'hex') "
            "WHERE tenant_id = :tenant AND last_seen_at IS NOT NULL "
            "AND last_seen_at < :cutoff AND display_name <> :tombstone"
        ),
        {
            "tombstone": TOMBSTONE,
            "prefix": f"{TOMBSTONE}:",
            "tenant": context.unit.tenant_id,
            "cutoff": _cutoff(clock, settings.retention_principal_days),
        },
    )
    return CollectorOutcome(items_written=result.rowcount or 0)


def retention_operational(
    context: CollectorContext, clock: Clock = _system_clock
) -> CollectorOutcome:
    """Remove run history, resolved errors and dead watermarks past the window.

    A watermark is one row per scope holding where that scope got to, so removing
    one is removing a resume point rather than removing history. That is the
    intent: a scope untouched for ninety days is a closed account or a region
    somebody stopped using, and if it ever returns, collecting it from the start
    is the correct behaviour rather than resuming from a three month old
    position. The window is three times the slowest cadence in
    `DEFAULT_SCHEDULE`, so a live scope cannot reach it.
    """
    settings = context.settings
    cutoff = _cutoff(clock, settings.retention_operational_days)
    tenant = context.unit.tenant_id
    removed = 0
    for target, stamp in (
        (_INGEST_RUN, "started_at"),
        (_SYNC_ERROR, "last_seen_at"),
        (_WATERMARK, "updated_at"),
    ):
        result = context.connection.execute(
            target.delete().where(target.c.tenant_id == tenant, target.c[stamp] < cutoff)
        )
        removed += result.rowcount or 0
    return CollectorOutcome(items_written=removed)


def retention_audit(context: CollectorContext, clock: Clock = _system_clock) -> CollectorOutcome:
    """Remove audit records past their own window, and only past their own window.

    This is the one path that may remove an audit record. An erasure request
    never can.
    """
    settings = context.settings
    result = context.connection.execute(
        _AUDIT_EVENT.delete().where(
            _AUDIT_EVENT.c.tenant_id == context.unit.tenant_id,
            _AUDIT_EVENT.c.occurred_at < _cutoff(clock, settings.retention_audit_days),
        )
    )
    return CollectorOutcome(items_written=result.rowcount or 0)


def retention_cost(context: CollectorContext, clock: Clock = _system_clock) -> CollectorOutcome:
    """Aggregate line items past the window to month, account, service and region,
    then remove them by dropping their partitions.

    The aggregate is written first and in the same transaction, so there is no
    instant at which the line items are gone and the monthly shape is not there.

    The boundary is the first of the month containing the cutoff, not the cutoff
    itself, because a partition is a whole month and a partition holding even one
    day inside the window cannot be removed. Aggregating on a different boundary
    to the one being dropped is how a month ends up counted twice or not at all.

    `cost_provider_extra` has no aggregate. It holds the provider's own fields
    that FOCUS has no column for, which are only meaningful against the line item
    they came from. Summing them would produce a number with no definition.
    """
    tenant = context.unit.tenant_id
    boundary = month_floor(_cutoff(clock, context.settings.retention_cost_days).date())
    at = clock()

    aggregated = context.connection.execute(
        text(
            "INSERT INTO cost_focus_monthly (tenant_id, billing_month, sub_account_id, "
            "service_name, region_id, billed_cost, effective_cost, line_items, as_of, "
            "collected_at) "
            "SELECT tenant_id, date_trunc('month', billing_period_start)::date, "
            "COALESCE(sub_account_id, ''), service_name, COALESCE(region_id, ''), "
            "SUM(billed_cost), SUM(effective_cost), COUNT(*), MIN(as_of), :at "
            "FROM cost_focus_daily WHERE tenant_id = :tenant AND billing_period_start < :boundary "
            "GROUP BY tenant_id, date_trunc('month', billing_period_start), "
            "COALESCE(sub_account_id, ''), service_name, COALESCE(region_id, '') "
            "ON CONFLICT (tenant_id, billing_month, sub_account_id, service_name, region_id) "
            "DO UPDATE SET billed_cost = EXCLUDED.billed_cost, "
            "effective_cost = EXCLUDED.effective_cost, line_items = EXCLUDED.line_items, "
            "collected_at = EXCLUDED.collected_at"
        ),
        {"tenant": tenant, "boundary": boundary, "at": at},
    ).rowcount

    # A partition is shared by every tenant, so it is only removed once the whole
    # month is past every tenant's window. Since the window is one setting for
    # the deployment, that is the same instant for all of them, and the tenant
    # filter above is what keeps the aggregate correct per tenant regardless.
    for parent in PARTITIONED_TABLES:
        detach_partitions_before(context.connection, parent, boundary)

    return CollectorOutcome(items_written=aggregated or 0)


def retention_scope_cache(
    context: CollectorContext, clock: Clock = _system_clock
) -> CollectorOutcome:
    """Remove expired entitlement cache rows. It is a cache, so this costs nothing."""
    result = context.connection.execute(
        _PRINCIPAL_SCOPE.delete().where(
            _PRINCIPAL_SCOPE.c.tenant_id == context.unit.tenant_id,
            _PRINCIPAL_SCOPE.c.expires_at < clock(),
        )
    )
    return CollectorOutcome(items_written=result.rowcount or 0)


#: The six, as collectors. Partition maintenance sits here rather than on its
#: own because it is the other half of the same job: one creates the months, the
#: other removes them, and splitting them across two modules is how the pair
#: drifts. All organization scoped: retention is a property of
#: a tenant's data and not of one account, and running it per account would run
#: it once per account over the same rows.
#:
#: A test holds these names equal to the retention names in `DEFAULT_SCHEDULE`.
#: Two lists of the same five things is exactly how a job ends up implemented and
#: never scheduled, which reads in production as a retention policy that quietly
#: never ran.
RETENTION_COLLECTORS: tuple[Collector, ...] = (
    Collector("retention_principal", CollectorScope.ORGANIZATION, retention_principal),
    Collector("retention_operational", CollectorScope.ORGANIZATION, retention_operational),
    Collector("retention_audit", CollectorScope.ORGANIZATION, retention_audit),
    Collector("retention_cost", CollectorScope.ORGANIZATION, retention_cost),
    Collector("partition_maintenance", CollectorScope.ORGANIZATION, partition_maintenance),
    Collector("retention_scope_cache", CollectorScope.ORGANIZATION, retention_scope_cache),
)


def register_retention(registry: Any) -> int:
    """Add the five to a registry. Returns how many, so a caller can assert on it."""
    for collector in RETENTION_COLLECTORS:
        registry.register(collector)
    return len(RETENTION_COLLECTORS)
