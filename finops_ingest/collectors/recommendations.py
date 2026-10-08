"""Bringing AWS's own findings into our table and our lifecycle.

Three services, one table, and three rules that are all about not losing what a
human did.

**A withdrawn recommendation is dismissed, not deleted.** When AWS stops reporting
a finding, the row stays and moves to `DISMISSED` with a reason naming the
withdrawal. Deleting it would take its whole event log with it, and the event log
is the only record that somebody accepted it in March and nothing happened.

**A recommendation a human has touched is not reopened.** The provider owns the
finding; we own the lifecycle. A re read that reset an `ACCEPTED` row to `OPEN`
every six hours would make the screen useless and the acceptance meaningless.

**One service failing does not fail the others.** Compute Optimizer needs an opt
in, Trusted Advisor needs a support tier, and an estate may have one and not the
other. Each is read in its own try, its refusal is recorded, and the rest continue.

**One account or Region failing does not fail its service either**, TASK-P9-006. A
source that reads scope by scope returns `ScopedFindings`: each refusal is recorded in
`sync_error`, and only a finding in a scope that was read can be withdrawn, so an
account that timed out keeps its findings rather than seeing them dismissed.

**Every ranked option is kept and priced from the catalog**, P9 spec section 5.5. An
option is priced at the catalog's newest EC2 version for its Region, at the Linux on
demand comparable price, or kept with the reason it could not be. The recommendation's
current and target prices are set from that same version, so a saving is only ever
the difference of two prices that exist together. The operating system is Linux until
the instance's own is read from its bill line, which TASK-P9-007 does.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from finops_core.domain.waste import Lifecycle, RankedOption, Recommendation, ScopedFindings, Source
from finops_core.errors import CollectionError, NotOptedIn
from finops_ingest.collectors.price_catalog import refuse
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "recommendations"
SCOPE = "billing"

Clock = Callable[[], datetime]


def _system_clock() -> datetime:
    return datetime.now(UTC)


#: Lifecycles a re read may overwrite. Everything else has been touched by a
#: person, and the provider does not get to undo that.
UNTOUCHED = (Lifecycle.OPEN.value, Lifecycle.DISMISSED.value)

WRITE = text(
    "INSERT INTO recommendation (recommendation_id, tenant_id, sub_account_id, source, "
    "source_reference, waste_class, resource_id, region_id, estimated_monthly_saving, "
    "confidence, severity, observation_days, lifecycle, owner, ticket_reference, "
    "rationale, as_of, collected_at) "
    "VALUES (:id, :tenant, :account, :source, :reference, :waste_class, :resource, :region, "
    ":saving, :confidence, :severity, :days, :lifecycle, NULL, NULL, :rationale, :as_of, :now) "
    "ON CONFLICT (tenant_id, source, source_reference) DO UPDATE SET "
    "estimated_monthly_saving = EXCLUDED.estimated_monthly_saving, "
    "confidence = EXCLUDED.confidence, severity = EXCLUDED.severity, "
    "observation_days = EXCLUDED.observation_days, rationale = EXCLUDED.rationale, "
    "waste_class = EXCLUDED.waste_class, as_of = EXCLUDED.as_of, "
    "collected_at = EXCLUDED.collected_at, "
    # The lifecycle is ours. A provider re read refreshes the money and the
    # working and leaves where the recommendation got to alone, unless nobody has
    # moved it, in which case reopening a previously withdrawn finding is right.
    "lifecycle = CASE WHEN recommendation.lifecycle IN ('OPEN', 'DISMISSED') "
    "THEN 'OPEN' ELSE recommendation.lifecycle END "
    "RETURNING recommendation_id"
)

#: The first event of a recommendation's life. Written only when the row is new,
#: because the constraint allows exactly one null `from_lifecycle` per row.
FIRST_EVENT = text(
    "INSERT INTO recommendation_event (event_id, recommendation_id, tenant_id, "
    "from_lifecycle, to_lifecycle, actor, reason, occurred_at, as_of, collected_at) "
    "SELECT :id, r.recommendation_id, :tenant, NULL, 'OPEN', :actor, :reason, :now, :now, :now "
    "FROM recommendation r "
    "WHERE r.tenant_id = :tenant AND r.source = :source AND r.source_reference = :reference "
    "AND NOT EXISTS ("
    "  SELECT 1 FROM recommendation_event e WHERE e.recommendation_id = r.recommendation_id"
    ")"
)

#: What this run did not see. Dismissed rather than deleted.
#:
#: A CTE rather than a plain UPDATE with RETURNING, and the reason is not style.
#: Postgres returns the **new** row from RETURNING, so `RETURNING lifecycle` on
#: this statement yields 'DISMISSED' for every row, and the event written from it
#: would read "DISMISSED to DISMISSED" for every withdrawal. The old value has to
#: be captured before the write, which is what the first arm does.
#:
#: `IN_PROGRESS` is deliberately absent from the filter. If somebody is actively
#: doing the work, a provider that stopped reporting the finding has most likely
#: noticed the work, and dismissing it out from under them would lose the fact
#: that it was being done.
_WITHDRAW = (
    "WITH going AS ("
    "  SELECT recommendation_id, lifecycle AS was FROM recommendation"
    "  WHERE tenant_id = :tenant AND source = :source"
    "    AND lifecycle IN ('OPEN', 'ACCEPTED')"
    "    AND source_reference <> ALL(:seen){scope}"
    "  FOR UPDATE"
    "), done AS ("
    "  UPDATE recommendation r SET lifecycle = 'DISMISSED', collected_at = :now"
    "  FROM going g WHERE r.recommendation_id = g.recommendation_id"
    "  RETURNING r.recommendation_id"
    ") SELECT recommendation_id, was FROM going"
)
WITHDRAW = text(_WITHDRAW.format(scope=""))
#: The same, inside the scopes a source read: an account in a Region, or every account in a
#: Region read without naming one. TASK-P9-006.
WITHDRAW_SCOPED = text(
    _WITHDRAW.format(
        scope=" AND ((sub_account_id || '|' || region_id) = ANY(:pairs)"
        " OR region_id = ANY(:anywhere))"
    )
)

WITHDRAW_EVENT = text(
    "INSERT INTO recommendation_event (event_id, recommendation_id, tenant_id, "
    "from_lifecycle, to_lifecycle, actor, reason, occurred_at, as_of, collected_at) "
    "VALUES (:id, :recommendation, :tenant, :from, 'DISMISSED', :actor, :reason, :now, :now, :now)"
)


#: The newest EC2 price list version the catalog holds for a Region.
LATEST_VERSION = text(
    "SELECT version FROM price_list_version WHERE tenant_id = :t AND service_code = 'AmazonEC2' "
    "AND region = :r ORDER BY as_of DESC LIMIT 1"
)
#: A type's comparable on demand price in one version: Linux, shared tenancy, used capacity,
#: nothing preinstalled, no licence, and not an Extended Support surcharge, FEAT-071.
PRICE_OF = text(
    "SELECT sku_price_id, recurring_unit_price FROM price "
    "WHERE tenant_id = :t AND service_code = 'AmazonEC2' AND region = :r AND version = :v "
    "AND pricing_category = 'Standard' AND pricing_unit = 'Hrs' "
    "AND sku_price_details ->> 'instanceType' = :type "
    "AND sku_price_details ->> 'operatingSystem' = 'Linux' "
    "AND coalesce(sku_price_details ->> 'tenancy', 'Shared') = 'Shared' "
    "AND coalesce(sku_price_details ->> 'capacitystatus', 'Used') = 'Used' "
    "AND coalesce(sku_price_details ->> 'preInstalledSw', 'NA') = 'NA' "
    "AND coalesce(sku_price_details ->> 'licenseModel', 'No License required') "
    "= 'No License required' "
    "AND (sku_price_details ->> 'extendedSupport') IS NULL "
    "ORDER BY sku_price_id LIMIT 1"
)
CLEAR_OPTIONS = text(
    "DELETE FROM recommendation_option WHERE tenant_id = :t AND recommendation_id = :id"
)
WRITE_OPTION = text(
    "INSERT INTO recommendation_option (option_pk, tenant_id, recommendation_id, region, rank, "
    "instance_type, performance_risk, provider_monthly_saving, migration_effort, "
    "platform_differences, sku_price_id, price_version, hourly_price, unpriced_reason, as_of, "
    "collected_at) VALUES (:pk, :t, :id, :r, :rank, :type, :risk, :saving, :effort, "
    ":differences, :sku, :v, :hourly, :reason, :as_of, :now)"
)
#: The recommendation's own current and target prices, from the version its options used.
SET_PRICES = text(
    "UPDATE recommendation SET current_sku_price_id = :current, "
    "target_instance_type = :target_type, target_sku_price_id = :target, price_version = :v "
    "WHERE recommendation_id = :id"
)


class RecommendationCollector:
    """Reads three services and writes one table."""

    def __init__(self, provider: Any, clock: Clock = _system_clock) -> None:
        self._provider = provider
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        now = self._clock()
        written = 0
        for source, read in (
            (Source.COMPUTE_OPTIMIZER, self._provider.compute_optimizer),
            (Source.COST_OPTIMIZATION_HUB, self._provider.cost_optimization_hub),
            (Source.TRUSTED_ADVISOR, self._provider.trusted_advisor),
        ):
            written += self._one_source(context, source, read, now)
        return CollectorOutcome(items_written=written)

    def _one_source(
        self,
        context: CollectorContext,
        source: Source,
        read: Callable[[], Iterable[Recommendation]],
        now: datetime,
    ) -> int:
        try:
            result = read()
            found = tuple(result)
        except NotOptedIn:
            # An expected state. The estate is correctly configured and has fewer
            # signals, and nothing is withdrawn: a service that was never on has
            # not stopped reporting anything.
            return 0
        except CollectionError:
            # Typed and real. The run continues with the other two services, and
            # the dispatcher records the failure. Withdrawing here would dismiss
            # every finding from a service that merely timed out.
            raise

        scopes: frozenset[tuple[str, str]] | None = None
        if isinstance(result, ScopedFindings):
            # Recorded and not raised: the scopes that were read still count, constraint 5.
            for failure in result.refused:
                refuse(context, COLLECTOR, failure, now)
            scopes = result.read

        for item in found:
            self._write(context, item, now)

        self._withdraw(context, source, [item.source_reference for item in found], now, scopes)
        return len(found)

    def _write(self, context: CollectorContext, item: Recommendation, now: datetime) -> None:
        recommendation_id = context.connection.execute(
            WRITE,
            {
                "id": uuid4(),
                "tenant": context.unit.tenant_id,
                "account": item.sub_account_id,
                "source": item.source.value,
                "reference": item.source_reference,
                "waste_class": item.waste_class.value,
                "resource": item.resource_id,
                "region": item.region_id,
                "saving": item.estimated_monthly_saving,
                "confidence": item.confidence.value,
                "severity": item.severity,
                "days": item.observation_days,
                "lifecycle": Lifecycle.OPEN.value,
                "rationale": item.rationale,
                "as_of": item.as_of,
                "now": now,
            },
        ).scalar_one()
        if item.options:
            self._price_options(context, recommendation_id, item, now)
        context.connection.execute(
            FIRST_EVENT,
            {
                "id": uuid4(),
                "tenant": context.unit.tenant_id,
                "source": item.source.value,
                "reference": item.source_reference,
                "actor": f"collector:{COLLECTOR}",
                "reason": None,
                "now": now,
            },
        )

    def _price_options(
        self,
        context: CollectorContext,
        recommendation_id: object,
        item: Recommendation,
        now: datetime,
    ) -> None:
        """Replace a recommendation's options, each priced from one catalog version or not."""
        tenant, region = context.unit.tenant_id, item.region_id
        connection = context.connection
        version = connection.execute(LATEST_VERSION, {"t": tenant, "r": region}).scalar()
        connection.execute(CLEAR_OPTIONS, {"t": tenant, "id": recommendation_id})

        def priced(instance_type: str | None) -> tuple[str, object] | None:
            if version is None or not instance_type:
                return None
            row = connection.execute(
                PRICE_OF, {"t": tenant, "r": region, "v": version, "type": instance_type}
            ).first()
            return None if row is None else (str(row[0]), row[1])

        prices: dict[int, tuple[str, object] | None] = {}
        for option in item.options:
            prices[option.rank] = found = priced(option.instance_type)
            connection.execute(
                WRITE_OPTION,
                {
                    **_option_row(option, found, version, region),
                    "pk": uuid4(),
                    "t": tenant,
                    "id": recommendation_id,
                    "r": region,
                    "as_of": item.as_of,
                    "now": now,
                },
            )
        best = min(item.options, key=lambda option: option.rank)
        target, current = prices[best.rank], priced(item.current_instance_type)
        connection.execute(
            SET_PRICES,
            {
                "id": recommendation_id,
                "current": current[0] if current else None,
                "target_type": best.instance_type if target else None,
                "target": target[0] if target else None,
                "v": version if (target or current) else None,
            },
        )

    def _withdraw(
        self,
        context: CollectorContext,
        source: Source,
        seen: list[str],
        now: datetime,
        scopes: frozenset[tuple[str, str]] | None = None,
    ) -> None:
        """Dismiss what this run did not see, keeping the row and its history.

        Inside the scopes a scoped source read, and nowhere else: a finding in an account
        that could not be read was not seen to go, so it stays.
        """
        parameters: dict[str, object] = {
            "tenant": context.unit.tenant_id,
            "source": source.value,
            # An empty list is a real answer: the service returned nothing, so
            # everything it previously reported has been withdrawn.
            "seen": seen or [""],
            "now": now,
        }
        if scopes is None:
            statement = WITHDRAW
        else:
            statement = WITHDRAW_SCOPED
            parameters["pairs"] = [f"{a}|{r}" for a, r in scopes if a != "*"] or [""]
            parameters["anywhere"] = [r for a, r in scopes if a == "*"] or [""]
        gone = context.connection.execute(statement, parameters).all()
        for row in gone:
            context.connection.execute(
                WITHDRAW_EVENT,
                {
                    "id": uuid4(),
                    "recommendation": row[0],
                    "tenant": context.unit.tenant_id,
                    "from": row[1],
                    "actor": f"collector:{COLLECTOR}",
                    "reason": f"{source.value} no longer reports this finding",
                    "now": now,
                },
            )


def _option_row(
    option: RankedOption, price: tuple[str, object] | None, version: str | None, region: str
) -> dict[str, object]:
    """An option's columns: its price from the catalog, or the reason it has none."""
    if price is None:
        reason: str | None = (
            f"the catalog holds no EC2 price list for {region}"
            if version is None
            else f"the catalog holds no Linux on demand price for {option.instance_type} "
            f"in {region}"
        )
    else:
        reason = None
    return {
        "rank": option.rank,
        "type": option.instance_type,
        "risk": option.performance_risk,
        "saving": option.provider_monthly_saving,
        "effort": option.migration_effort,
        "differences": list(option.platform_differences),
        "sku": price[0] if price else None,
        "v": version if price else None,
        "hourly": price[1] if price else None,
        "reason": reason,
    }
