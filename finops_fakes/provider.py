"""An in memory provider that satisfies all eight provider ports, failures included.

The point of this class is not that it succeeds. It is that any of the six
causes can be planned for any scope, so a failure path is as cheap to test as a
success path. The three behaviours this project cares most about are all
failures, and a fake that can only succeed leaves every one of them untested.

Passing `failures` replaces the fixture plan rather than merging with it, so a
test states exactly what fails and never inherits a rule it cannot see.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any

from finops_core.domain.account import AccountKey, CloudAccount
from finops_core.domain.containers import ClusterSlice, ReservationVsUse
from finops_core.domain.cost import CommitmentCoverage, CommitmentDay, CommitmentUse, CostRecord
from finops_core.domain.identity import Entitlement, Principal
from finops_core.domain.metrics import MetricPoint
from finops_core.domain.org import OrgNode
from finops_core.domain.quota import QuotaIncreaseRequest, QuotaUsage
from finops_core.domain.resource import ResourceRef
from finops_core.domain.tenant import Scope
from finops_core.domain.topology import CoverageCause, Shortfall, SliceRead
from finops_core.errors import AccessDenied, CollectionError
from finops_core.ports.metrics import MetricRequest
from finops_fakes import fixtures
from finops_fakes.commitment import FakeCommitmentReport
from finops_fakes.containers import FakeContainerSource
from finops_fakes.cur import FakeCostExport
from finops_fakes.topology import AGGREGATOR, FakeTopologySource

COLLECTOR = "fake"


@dataclass(frozen=True)
class FakeSession:
    """What `session_for` hands back. Opaque, like the real thing."""

    account: AccountKey
    region: str
    expires_at: datetime


def _restamp(facts: tuple[Any, ...], at: datetime | None) -> tuple[Any, ...]:
    """The same facts, observed now. Unchanged when no time is given."""
    if at is None:
        return facts
    return tuple(replace(fact, as_of=at, collected_at=at) for fact in facts)


class FakeProvider:
    """One object satisfying every provider port, with a configurable failure plan.

    The count is deliberately not in this sentence. It said eight until P6 added a
    ninth, and `tests/core/test_ports.py` is where the number belongs.
    """

    def __init__(
        self,
        accounts: tuple[CloudAccount, ...] | None = None,
        nodes: tuple[OrgNode, ...] | None = None,
        failures: Mapping[str, type[CollectionError]] | None = None,
        at: datetime | None = None,
    ) -> None:
        # `at` restamps the fixtures rather than replacing them. The constants
        # carry a date from 2026-08-24, which is right for a test asserting a
        # value and wrong for a demo estate, where it made two screens read as
        # five days stale beside four that read as current. ISS-161.
        # Kept, so the container source can be built at the same instant. It is the
        # only port here whose data is generated per call rather than restamped.
        self._at = at or fixtures.AS_OF
        self._accounts = _restamp(fixtures.ACCOUNTS if accounts is None else accounts, at)
        self._nodes = _restamp(fixtures.ORG_NODES if nodes is None else nodes, at)
        self._failures: Mapping[str, type[CollectionError]] = (
            dict(fixtures.DEFAULT_FAILURES) if failures is None else dict(failures)
        )
        # The smoke fixture, not the richer estate. This provider's cost rows
        # are asserted against by tests that predate P1, and a provider that
        # silently grew from four rows to two thousand would change what every
        # one of them means. The failure plan above still governs, because it is
        # this provider's plan and not the export's.
        self._cost = FakeCostExport(rows=fixtures.COST_ROWS)
        self._commitment = FakeCommitmentReport()

    # -- the failure plan --------------------------------------------------

    def _fail_if_planned(self, scope_key: str) -> None:
        planned = self._failures.get(scope_key)
        if planned is not None:
            raise planned(
                scope_key=scope_key,
                collector=COLLECTOR,
                detail="planned by the fake provider",
            )

    def _known(self, account: AccountKey) -> bool:
        return any(existing.key == account for existing in self._accounts)

    def _require_known(self, account: AccountKey, region: str | None = None) -> None:
        # The scope key format is the one docs/07-DATA-MODEL.md documents,
        # provider:account:region. The contract suite caught this diverging from
        # the AWS adapter, which is exactly what it is for.
        scope_key = str(account) if region is None else f"{account}:{region}"
        # A plan may be keyed on either form, and whichever matched, the error
        # carries the most specific key so a reader can tell which region failed.
        planned = self._failures.get(scope_key) or self._failures.get(str(account))
        if planned is not None:
            raise planned(
                scope_key=scope_key,
                collector=COLLECTOR,
                detail="planned by the fake provider",
            )
        if not self._known(account):
            raise AccessDenied(
                scope_key=scope_key,
                collector=COLLECTOR,
                detail="the fixture organization does not contain this account",
            )

    # -- TopologySource ----------------------------------------------------

    @property
    def enrolled_slices(self) -> tuple[tuple[AccountKey, str | None], ...]:
        return FakeTopologySource().enrolled_slices

    def read_slice(self, account: AccountKey, region: str | None) -> SliceRead:
        """One slice of the generated estate, with what it could not read named.

        **A planned failure becomes a shortfall here, not an exception.** Every other
        method on this class raises the planned error, because for every other port a
        refusal means the answer is unknown and unknown is not zero. This port reports
        on partial success, so a refusal that reached the caller as an exception would
        discard the slices already read and leave nothing to write a PARTIAL coverage
        row from. The contract asserts it for both providers.

        An account the fixture organization does not contain still raises, because
        that is not a fact about the estate: no slice was read and there is nothing
        partial to report.
        """
        if not self._known(account):
            raise AccessDenied(
                scope_key=str(account),
                collector=COLLECTOR,
                detail="the fixture organization does not contain this account",
            )
        scope_key = str(account) if region is None else f"{account}:{region}"
        planned = self._failures.get(scope_key) or self._failures.get(str(account))
        if planned is not None:
            return SliceRead(
                account_key=account,
                region_id=region,
                nodes=(),
                edges=(),
                shortfalls=(
                    Shortfall(
                        source=AGGREGATOR,
                        cause=CoverageCause(planned.cause),
                        detail="planned by the fake provider",
                    ),
                ),
            )
        return FakeTopologySource().read_slice(account, region)

    # -- CredentialBroker --------------------------------------------------

    def session_for(self, account: AccountKey, region: str) -> FakeSession:
        self._require_known(account, region)
        return FakeSession(account=account, region=region, expires_at=fixtures.SESSION_EXPIRES_AT)

    # -- AccountDiscovery --------------------------------------------------

    def list_accounts(self) -> Iterable[CloudAccount]:
        self._fail_if_planned(fixtures.ORGANIZATION_SCOPE)
        # Including the account that denies access is deliberate. An account we
        # cannot read is still an account, and omitting it hides the gap rather
        # than reporting it.
        return tuple(self._accounts)

    def describe_organization(self) -> Iterable[OrgNode]:
        self._fail_if_planned(fixtures.ORGANIZATION_SCOPE)
        return tuple(self._nodes)

    # -- CostExport --------------------------------------------------------

    # Delegated to `FakeCostExport` rather than implemented again here. Two
    # fakes for one port is two places a behaviour can drift, and the port's
    # `NoData` rule is exactly the kind of thing that drifts. This keeps the
    # four row smoke fixture as the estate, so every test that already asserts
    # against it still sees what it saw; the richer estate is the default when
    # `FakeCostExport` is constructed on its own.

    def latest_available_period(self) -> date | None:
        self._fail_if_planned(fixtures.ORGANIZATION_SCOPE)
        return self._cost.latest_available_period()

    def read_period(self, period_start: date, period_end: date) -> Iterable[CostRecord]:
        self._fail_if_planned(fixtures.ORGANIZATION_SCOPE)
        return self._cost.read_period(period_start, period_end)

    # -- CommitmentReport --------------------------------------------------

    # Delegated for the same reason as `CostExport`: two implementations of one
    # answer is two answers. The failure plan is checked here as well, because a
    # provider planned to fail should fail on every port and not only the ones
    # that remembered to ask.

    def utilization(self, window_start: date, window_end: date) -> Iterable[CommitmentUse]:
        self._fail_if_planned(fixtures.ORGANIZATION_SCOPE)
        return self._commitment.utilization(window_start, window_end)

    def coverage(self, window_start: date, window_end: date) -> Iterable[CommitmentCoverage]:
        self._fail_if_planned(fixtures.ORGANIZATION_SCOPE)
        return self._commitment.coverage(window_start, window_end)

    def daily(self, window_start: date, window_end: date) -> Iterable[CommitmentDay]:
        self._fail_if_planned(fixtures.ORGANIZATION_SCOPE)
        return self._commitment.daily(window_start, window_end)

    # -- MetricSource ------------------------------------------------------

    def read_series(
        self,
        account: AccountKey,
        region: str,
        namespace: str,
        metric_name: str,
        dimensions: Mapping[str, str],
        statistic: str,
        window_start: datetime,
        window_end: datetime,
    ) -> Iterable[MetricPoint]:
        self._require_known(account)
        return tuple(
            point for point in fixtures.METRIC_POINTS if window_start <= point.at <= window_end
        )

    def read_many(
        self,
        requests: Iterable[MetricRequest],
        window_start: datetime,
        window_end: datetime,
        period_seconds: int = 3600,
    ) -> Mapping[str, tuple[MetricPoint, ...]]:
        """The batched read, over the same fixture `read_series` uses.

        A key is absent where its account is one this provider refuses, rather
        than empty, because the port says an unobserved series does not appear and
        a caller must tell that from a series of zeroes. The refusal is per
        request here rather than raised for the batch, since a batch that failed
        entirely because one account was denied would be unusable at the scale the
        method exists for.
        """
        found: dict[str, tuple[MetricPoint, ...]] = {}
        for request in requests:
            if request.account not in fixtures.ACCOUNT_KEYS:
                continue
            points = tuple(
                point for point in fixtures.METRIC_POINTS if window_start <= point.at <= window_end
            )
            if points:
                found[request.key] = points
        return found

    # -- ResourceInventory -------------------------------------------------

    def list_resources(
        self, account: AccountKey, region: str, resource_type: str | None = None
    ) -> Iterable[ResourceRef]:
        self._require_known(account)
        return tuple(
            ref
            for ref in fixtures.RESOURCES
            if resource_type is None or ref.resource_type == resource_type
        )

    def list_dependencies(self, account: AccountKey, resource_id: str) -> Iterable[ResourceRef]:
        self._require_known(account)
        return tuple(ref for ref in fixtures.RESOURCES if ref.resource_id != resource_id)

    # -- QuotaSource -------------------------------------------------------

    def list_quotas(self, account: AccountKey, region: str) -> Iterable[QuotaUsage]:
        self._require_known(account)
        return tuple(fixtures.QUOTAS)

    def requests(self, account: AccountKey, region: str) -> Iterable[QuotaIncreaseRequest]:
        self._require_known(account)
        return tuple(fixtures.QUOTA_REQUESTS)

    # -- ContainerSource ---------------------------------------------------

    def list_clusters(self, account: AccountKey, region: str) -> Iterable[ClusterSlice]:
        self._require_known(account)
        return FakeContainerSource(at=self._at).list_clusters(account, region)

    def reservations(self, account: AccountKey, region: str) -> Iterable[ReservationVsUse]:
        self._require_known(account)
        return FakeContainerSource(at=self._at).reservations(account, region)

    # -- IdentityProvider --------------------------------------------------

    def authenticate(self, token: str) -> Principal:
        if token != fixtures.VALID_TOKEN:
            # Absent, expired and forged are one answer on purpose. Telling the
            # caller which is a free oracle for whoever is guessing.
            raise AccessDenied(
                scope_key="principal:unknown",
                collector=COLLECTOR,
                detail="the token was not issued by this provider",
            )
        return fixtures.PRINCIPAL

    # -- EntitlementResolver -----------------------------------------------

    def resolve(self, principal: Principal) -> Entitlement:
        known = principal == fixtures.PRINCIPAL
        scope = Scope(
            tenant_id=fixtures.TENANT_ID,
            is_global=False,
            # An unknown principal gets nothing rather than an exception. Empty
            # fails closed, and an exception here tempts a caller into a
            # fallback that does not.
            accounts=frozenset(fixtures.ACCOUNT_KEYS) if known else frozenset(),
        )
        return Entitlement(
            principal=principal,
            scope=scope,
            as_of=fixtures.AS_OF,
            collected_at=fixtures.COLLECTED_AT,
        )
