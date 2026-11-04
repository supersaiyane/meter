"""An in memory provider that satisfies all eight ports, failures included.

The point of this class is not that it succeeds. It is that any of the six
causes can be planned for any scope, so a failure path is as cheap to test as a
success path. The three behaviours this project cares most about are all
failures, and a fake that can only succeed leaves every one of them untested.

Passing `failures` replaces the fixture plan rather than merging with it, so a
test states exactly what fails and never inherits a rule it cannot see.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime

from finops_core.domain.account import AccountKey, CloudAccount
from finops_core.domain.cost import CostRecord
from finops_core.domain.identity import Entitlement, Principal
from finops_core.domain.metrics import MetricPoint
from finops_core.domain.org import OrgNode
from finops_core.domain.quota import QuotaUsage
from finops_core.domain.resource import ResourceRef
from finops_core.domain.tenant import Scope
from finops_core.errors import AccessDenied, CollectionError, NoData
from finops_providers.fake import fixtures

COLLECTOR = "fake"


@dataclass(frozen=True)
class FakeSession:
    """What `session_for` hands back. Opaque, like the real thing."""

    account: AccountKey
    region: str
    expires_at: datetime


class FakeProvider:
    """One object satisfying all eight ports, with a configurable failure plan."""

    def __init__(
        self,
        accounts: tuple[CloudAccount, ...] | None = None,
        nodes: tuple[OrgNode, ...] | None = None,
        failures: Mapping[str, type[CollectionError]] | None = None,
    ) -> None:
        self._accounts = fixtures.ACCOUNTS if accounts is None else accounts
        self._nodes = fixtures.ORG_NODES if nodes is None else nodes
        self._failures: Mapping[str, type[CollectionError]] = (
            dict(fixtures.DEFAULT_FAILURES) if failures is None else dict(failures)
        )

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

    def latest_available_period(self) -> date | None:
        self._fail_if_planned(fixtures.ORGANIZATION_SCOPE)
        return fixtures.PERIOD_START

    def read_period(self, period_start: date, period_end: date) -> Iterable[CostRecord]:
        self._fail_if_planned(fixtures.ORGANIZATION_SCOPE)
        rows = tuple(
            row
            for row in fixtures.COST_ROWS
            if row.billing_period_start >= period_start and row.billing_period_end <= period_end
        )
        if not rows:
            raise NoData(
                scope_key=fixtures.ORGANIZATION_SCOPE,
                collector=COLLECTOR,
                detail=f"the fixture holds no rows between {period_start} and {period_end}",
            )
        return rows

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
