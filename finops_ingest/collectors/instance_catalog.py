"""What each instance type is, in every Region it is sold in. FEAT-072, TASK-P9-005.

P9 spec sections 5.4 and 14.3.

**EC2 is described once and placed by its prices.** EC2's description of a type is read in the
hub's own Region, and the type is stored for every Region the price catalog sells it in, read
from the `price` rows FEAT-071 stores, so no Region is named here. That rests on a type being
described alike everywhere, and the spec asks for the assumption to be held rather than trusted:
when a second Region is configured, its description is read too and any type described
differently is SchemaDrift in `sync_error` and is stored only in the hub's Region. A type the
price list sells that the hub's Region does not describe has no description to place, and is
counted as NoData rather than guessed. Every run rewrites EC2's rows, because a description
carries no version to compare: about 900 types in about 30 Regions (modelled), three times a day.

**The managed services are described where their prices are.** RDS, ElastiCache, Redshift and
OpenSearch are read Region by Region from their price list products, and only in a Region whose
price list version is newer than the description already held, so a run that finds nothing new
reads nothing.

**A burstable type with no baseline is not stored.** The database refuses one, constraint 11, and
a type with no baseline would be read as able to run flat out for nothing. It is counted as NoData
with its name instead, so the table in `finops_providers/aws/burstable.py` is visibly short.

**Withdrawn types stay, marked.** A type a Region no longer lists is set `offered = false` rather
than deleted, because a recommendation written last week may still name it.

**One Region or service failing does not fail the run**, constraint 5: it is recorded in
`sync_error` by its typed cause. Only a run that read nothing at all fails.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Final
from uuid import uuid4

from sqlalchemy import text

from finops_core.domain.catalog import InstanceTypeSpec
from finops_core.errors import CollectionError, NoData, SchemaDrift
from finops_core.ports.catalog import InstanceCatalog
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "instance_catalog"
EC2: Final = "AmazonEC2"
#: How many names a refusal lists before it says how many more there are.
NAMED: Final = 5

#: Where the price catalog sells each EC2 type.
SOLD = text(
    "SELECT DISTINCT region, sku_price_details ->> 'instanceType' AS instance_type FROM price "
    "WHERE tenant_id = :t AND service_code = :s "
    "AND (sku_price_details ->> 'instanceType') IS NOT NULL"
)

#: The newest price list a service has in each Region, and the newest description held there.
LISTED = text(
    "SELECT region, max(as_of) AS as_of FROM price_list_version "
    "WHERE tenant_id = :t AND service_code = :s GROUP BY region"
)
DESCRIBED = text(
    "SELECT region, max(as_of) AS as_of FROM instance_type_spec "
    "WHERE tenant_id = :t AND service_code = :s AND offered GROUP BY region"
)

WRITE = text(
    "INSERT INTO instance_type_spec (spec_pk, tenant_id, ingest_run_id, service_code, region, "
    "instance_type, family, current_generation, architectures, burstable, baseline_cpu, "
    "maximum_credits, baseline_source, vcpus, memory_mib, network_performance, "
    "network_baseline_gbps, network_peak_gbps, ebs_baseline_mbps, ebs_maximum_mbps, gpu_count, "
    "offered, as_of, collected_at) "
    "VALUES (:pk, :t, :run, :s, :r, :type, :family, :current, :architectures, :burstable, "
    ":baseline, :credits, :source, :vcpus, :memory, :network, :net_base, :net_peak, :ebs_base, "
    ":ebs_max, :gpus, true, :as_of, :collected) "
    "ON CONFLICT (tenant_id, service_code, region, instance_type) DO UPDATE SET "
    "ingest_run_id = EXCLUDED.ingest_run_id, family = EXCLUDED.family, "
    "current_generation = EXCLUDED.current_generation, architectures = EXCLUDED.architectures, "
    "burstable = EXCLUDED.burstable, baseline_cpu = EXCLUDED.baseline_cpu, "
    "maximum_credits = EXCLUDED.maximum_credits, baseline_source = EXCLUDED.baseline_source, "
    "vcpus = EXCLUDED.vcpus, memory_mib = EXCLUDED.memory_mib, "
    "network_performance = EXCLUDED.network_performance, "
    "network_baseline_gbps = EXCLUDED.network_baseline_gbps, "
    "network_peak_gbps = EXCLUDED.network_peak_gbps, "
    "ebs_baseline_mbps = EXCLUDED.ebs_baseline_mbps, "
    "ebs_maximum_mbps = EXCLUDED.ebs_maximum_mbps, gpu_count = EXCLUDED.gpu_count, "
    "offered = true, as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at"
)

WITHDRAW = text(
    "UPDATE instance_type_spec SET offered = false "
    "WHERE tenant_id = :t AND service_code = :s AND region = :r AND offered "
    "AND ingest_run_id <> :run"
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


def _system_clock() -> datetime:
    return datetime.now(UTC)


Clock = Callable[[], datetime]


def _shape(spec: InstanceTypeSpec) -> tuple[Any, ...]:
    """What must read the same in two Regions for one description to stand for both."""
    return (
        spec.vcpus,
        spec.memory_mib,
        spec.architectures,
        spec.burstable,
        spec.current_generation,
        spec.network_performance,
        spec.network_baseline_gbps,
        spec.network_peak_gbps,
        spec.ebs_baseline_mbps,
        spec.ebs_maximum_mbps,
        spec.gpu_count,
    )


def _named(names: Iterable[str]) -> str:
    listed = sorted(names)
    shown = ", ".join(listed[:NAMED])
    more = len(listed) - NAMED
    return f"{shown} and {more} more" if more > 0 else shown


class _Run:
    """One run's writes, refusals and whether anything at all was read."""

    def __init__(self, context: CollectorContext, now: datetime) -> None:
        self.context = context
        self.now = now
        self.written = 0
        self.read = False
        self.failures: list[CollectionError] = []

    def refuse(self, failure: CollectionError) -> None:
        """A read that failed: recorded, and counted towards failing a run that read nothing."""
        self.failures.append(failure)
        self._record(failure)

    def note(self, failure: CollectionError) -> None:
        """A shortfall inside a read that succeeded: recorded, and not a reason to fail."""
        self._record(failure)

    def _record(self, failure: CollectionError) -> None:
        self.context.connection.execute(
            REFUSED,
            {
                "id": uuid4(),
                "t": self.context.unit.tenant_id,
                "c": COLLECTOR,
                "s": failure.scope_key,
                "type": failure.cause,
                "d": str(failure),
                "r": failure.remediation,
                "now": self.now,
            },
        )

    def store(self, service: str, region: str, specs: Iterable[InstanceTypeSpec]) -> None:
        context = self.context
        rows = [self._row(spec) for spec in specs]
        if rows:
            context.connection.execute(WRITE, rows)
        context.connection.execute(
            WITHDRAW,
            {"t": context.unit.tenant_id, "s": service, "r": region, "run": context.run_id},
        )
        self.written += len(rows)
        self.read = True

    def _row(self, spec: InstanceTypeSpec) -> dict[str, Any]:
        return {
            "pk": uuid4(),
            "t": self.context.unit.tenant_id,
            "run": self.context.run_id,
            "s": spec.service_code,
            "r": spec.region,
            "type": spec.instance_type,
            "family": spec.family,
            "current": spec.current_generation,
            "architectures": list(spec.architectures),
            "burstable": spec.burstable,
            "baseline": spec.baseline_cpu,
            "credits": spec.maximum_credits,
            "source": spec.baseline_source,
            "vcpus": spec.vcpus,
            "memory": spec.memory_mib,
            "network": spec.network_performance,
            "net_base": spec.network_baseline_gbps,
            "net_peak": spec.network_peak_gbps,
            "ebs_base": spec.ebs_baseline_mbps,
            "ebs_max": spec.ebs_maximum_mbps,
            "gpus": spec.gpu_count,
            "as_of": spec.as_of,
            "collected": spec.collected_at,
        }


class InstanceCatalogCollector:
    """EC2's types placed in every Region they are sold, and the managed services' classes."""

    def __init__(
        self,
        ec2: InstanceCatalog,
        *,
        hub_region: str,
        compare_region: str | None = None,
        managed: Mapping[str, InstanceCatalog] | None = None,
        clock: Clock = _system_clock,
    ) -> None:
        if compare_region == hub_region:
            raise ValueError("a description compared with itself proves nothing")
        self._ec2 = ec2
        self._hub = hub_region
        self._compare = compare_region
        self._managed = dict(managed or {})
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        run = _Run(context, self._clock())
        self._describe_ec2(run)
        for service, catalog in sorted(self._managed.items()):
            self._describe_managed(run, service, catalog)
        if run.failures and not run.read:
            raise run.failures[0]
        return CollectorOutcome(items_written=run.written)

    # --- EC2 ------------------------------------------------------------------------

    def _describe_ec2(self, run: _Run) -> None:
        try:
            described = {s.instance_type: s for s in self._ec2.instance_types(self._hub)}
        except CollectionError as failure:
            run.refuse(failure)
            return
        unbounded = self._unbounded(run, f"{EC2}:{self._hub}", described.values())
        local = self._differing(run, described)
        tenant = run.context.unit.tenant_id
        sold = {
            (row.region, row.instance_type)
            for row in run.context.connection.execute(SOLD, {"t": tenant, "s": EC2})
        }
        undescribed = {name for _, name in sold} - described.keys()
        if undescribed:
            run.note(
                NoData(
                    scope_key=f"{EC2}:undescribed",
                    collector=COLLECTOR,
                    detail=f"the price list sells types {self._hub} does not describe, so "
                    f"they have no description to place: {_named(undescribed)}",
                )
            )
        storable = {name: spec for name, spec in described.items() if name not in unbounded}
        regions = {self._hub} | {region for region, _ in sold}
        for region in sorted(regions):
            if region == self._hub:
                names = set(storable)
            else:
                sold_here = {name for where, name in sold if where == region}
                names = (sold_here & storable.keys()) - local
            run.store(EC2, region, (replace(storable[n], region=region) for n in sorted(names)))

    def _differing(self, run: _Run, described: Mapping[str, InstanceTypeSpec]) -> set[str]:
        """The types a second Region describes differently, stored only where they were read."""
        if self._compare is None:
            return set()
        try:
            other = {s.instance_type: s for s in self._ec2.instance_types(self._compare)}
        except CollectionError as failure:
            run.note(failure)
            return set()
        differing = {
            name
            for name in described.keys() & other.keys()
            if _shape(described[name]) != _shape(other[name])
        }
        if differing:
            run.note(
                SchemaDrift(
                    scope_key=f"{EC2}:{self._compare}",
                    collector=COLLECTOR,
                    detail=f"{len(differing)} types are described differently in "
                    f"{self._compare} than in {self._hub}, and are stored only in "
                    f"{self._hub}: {_named(differing)}",
                )
            )
        return differing

    # --- the managed services ---------------------------------------------------------

    def _describe_managed(self, run: _Run, service: str, catalog: InstanceCatalog) -> None:
        tenant = run.context.unit.tenant_id
        connection = run.context.connection
        listed = {
            r.region: r.as_of for r in connection.execute(LISTED, {"t": tenant, "s": service})
        }
        held = {
            r.region: r.as_of for r in connection.execute(DESCRIBED, {"t": tenant, "s": service})
        }
        for region in sorted(listed):
            if region in held and held[region] >= listed[region]:
                run.read = True
                continue
            try:
                specs = tuple(catalog.instance_types(region))
            except CollectionError as failure:
                run.refuse(failure)
                continue
            unbounded = self._unbounded(run, f"{service}:{region}", specs)
            run.store(service, region, (s for s in specs if s.instance_type not in unbounded))

    @staticmethod
    def _unbounded(run: _Run, scope: str, specs: Iterable[InstanceTypeSpec]) -> set[str]:
        """Burstable types the credit table has no baseline for, recorded and not stored."""
        unbounded = {s.instance_type for s in specs if s.burstable and s.baseline_cpu is None}
        if unbounded:
            run.note(
                NoData(
                    scope_key=f"{scope}:burstable",
                    collector=COLLECTOR,
                    detail="burstable types with no row in the EC2 guide's credit table, so "
                    f"no baseline and not stored: {_named(unbounded)}",
                )
            )
        return unbounded
