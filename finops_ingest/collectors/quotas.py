"""Every quota in a slice, and every increase request against it.

FEAT-033 and FEAT-034. The judgement lives in `finops_core/domain/quota.py` and the
reading in `finops_providers/aws/quotas.py`; this module stores what came back.

**It stores the quotas nothing can measure, and that is most of them.** A collector that
wrote only the measured ones would leave a screen reporting an estate with excellent
headroom everywhere, which is the outage this sub project exists to prevent. Each
unmeasured row carries a null usage, a source of NONE and the sentence saying which of the
three sources declined.

**A quota that stops publishing usage loses its figure rather than keeping it.** The upsert
overwrites `used_value` and `usage_source` on every run, so the day a metric stops
publishing the row becomes unmeasured and says so. Keeping the last known figure would be
the worse of the two failures: a stale number is indistinguishable from a current one, and
it is the one somebody acts on.

**Global quotas are written by every region's run, and that is deliberate.** IAM roles per
account belong to the account rather than to a region, so the adapter carries them in every
slice with a null region and the identity index treats two nulls as equal. Two regional
runs therefore write the same row twice and the second wins, which is idempotent and costs
one upsert. The alternative, electing one region to own them, means choosing a region in
code, and a deployment that stops using that region silently stops collecting every global
quota.

**Requests are read and never written.** Constraint 6 and spec section 6:
`RequestServiceQuotaIncrease` appears nowhere in this package, `submitted_by_meter` is a
column that can only say false, and the status history is stored so a screen can say when a
request was approved rather than only that it is.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import text

from finops_core.domain.quota import QuotaIncreaseRequest, QuotaUsage, UsageSource
from finops_core.errors import SchemaDrift
from finops_ingest.registry import CollectorContext, CollectorOutcome

COLLECTOR = "quotas"

#: Upserted on the quota's identity, which includes the region and treats two nulls as
#: equal. Every field a run can observe is overwritten, including the absences: a quota that
#: loses its usage metric has to lose its figure with it.
WRITE_QUOTA = text(
    "INSERT INTO quota_usage (quota_pk, tenant_id, ingest_run_id, sub_account_id, region_id, "
    "service_code, quota_code, quota_name, limit_value, used_value, usage_source, "
    "unmeasurable_reason, is_adjustable, as_of, collected_at) "
    "VALUES (:pk, :tenant, :run, :account, :region, :service, :quota, :name, :limit, :used, "
    ":source, :reason, :adjustable, :as_of, :collected) "
    "ON CONFLICT (tenant_id, sub_account_id, region_id, service_code, quota_code) DO UPDATE SET "
    "ingest_run_id = EXCLUDED.ingest_run_id, quota_name = EXCLUDED.quota_name, "
    "limit_value = EXCLUDED.limit_value, used_value = EXCLUDED.used_value, "
    "usage_source = EXCLUDED.usage_source, "
    "unmeasurable_reason = EXCLUDED.unmeasurable_reason, "
    "is_adjustable = EXCLUDED.is_adjustable, as_of = EXCLUDED.as_of, "
    "collected_at = EXCLUDED.collected_at"
)

#: What the provider stopped returning. Scoped to this slice and to rows this run did not
#: write, and it runs inside the worker's transaction, so a read that failed part way rolls
#: the removal back with it rather than emptying the slice.
#:
#: Global quota rows are included only when this run actually saw a global quota, and that
#: condition is load bearing rather than defensive. A global quota carries no region, so
#: nothing about the slice it arrived in says which run owns it. A provider reporting globals
#: in every region has written them all by the time the retraction runs; a provider reporting
#: them once, in one region, has not. Under an unconditional rule the second region's run
#: would delete every global quota the first had just written, on the strength of never having
#: been offered one. Asking whether this run saw any is the difference between a withdrawal
#: and an absence of evidence. The fake estate reports globals in one region only, which is
#: how the unconditional version was caught.
RETRACT_QUOTAS = text(
    "DELETE FROM quota_usage WHERE tenant_id = :tenant AND sub_account_id = :account "
    "AND (region_id = :region OR (:saw_global AND region_id IS NULL)) "
    "AND ingest_run_id <> :run"
)

#: Upserted on AWS's own request id. A request read twice is one row and its status moves in
#: place, because a second row would let a screen show one increase as two.
WRITE_REQUEST = text(
    "INSERT INTO quota_request (request_pk, tenant_id, ingest_run_id, request_id, "
    "sub_account_id, region_id, service_code, quota_code, desired_value, status, "
    "requested_at, last_updated_at, submitted_by_meter, as_of, collected_at) "
    "VALUES (:pk, :tenant, :run, :request, :account, :region, :service, :quota, :desired, "
    ":status, :requested, :updated, FALSE, :as_of, :collected) "
    "ON CONFLICT (tenant_id, request_id) DO UPDATE SET "
    "ingest_run_id = EXCLUDED.ingest_run_id, status = EXCLUDED.status, "
    "desired_value = EXCLUDED.desired_value, last_updated_at = EXCLUDED.last_updated_at, "
    "as_of = EXCLUDED.as_of, collected_at = EXCLUDED.collected_at"
)

#: One row per status per request, so the sequence survives. DO NOTHING because a transition
#: already recorded happened when it happened: rewriting `changed_at` on every collection
#: would walk the day a request was approved forward to today, one run at a time.
WRITE_HISTORY = text(
    "INSERT INTO quota_request_history (history_pk, tenant_id, request_id, status, changed_at) "
    "VALUES (:pk, :tenant, :request, :status, :changed) "
    "ON CONFLICT (tenant_id, request_id, status) DO NOTHING"
)

#: Trusted Advisor being unavailable is a real gap with a real fix, so it goes where an
#: operator looks rather than only into a reason on each row. Deliberately not written when
#: quotas are simply unpublished: that is the provider's limit rather than ours, and a
#: permanent error nobody can act on is how a screen of errors becomes one nobody reads.
ADVISOR_GAP = text(
    "INSERT INTO sync_error (error_id, tenant_id, collector, scope_key, error_type, "
    "detail, remediation, first_seen_at, last_seen_at, occurrences) "
    "VALUES (:id, :t, :c, :s, 'NotOptedIn', :d, :r, :now, :now, 1) "
    "ON CONFLICT (tenant_id, collector, scope_key, error_type) DO UPDATE SET "
    "detail = EXCLUDED.detail, last_seen_at = EXCLUDED.last_seen_at, "
    "occurrences = sync_error.occurrences + 1"
)

#: What marks a reason as the support tier rather than the provider's own limit. The cause
#: name is the only thing the adapter and this module agree on without one importing the
#: other's prose, and the adapter puts it in the sentence for exactly this reason.
ADVISOR_MARKER = "NotOptedIn"


def _system_clock() -> datetime:
    return datetime.now(UTC)


Clock = Callable[[], datetime]


class QuotaCollector:
    """Quotas and increase requests for one account in one region."""

    def __init__(self, source: Any, clock: Clock = _system_clock) -> None:
        self._source = source
        self._clock = clock

    def __call__(self, context: CollectorContext) -> CollectorOutcome:
        now = self._clock()
        unit = context.unit
        if unit.account is None or unit.region is None:
            # A quota is per account per region, so a unit missing either names no slice.
            # Refused as drift rather than defaulted: a default region would collect one
            # region's quotas and file them under every other.
            raise SchemaDrift(
                scope_key=unit.scope_key,
                collector=COLLECTOR,
                detail="a quota unit arrived without an account or a region",
            )
        account = unit.account.account_id
        region = unit.region

        quotas = tuple(self._source.list_quotas(unit.account, region))
        for quota in quotas:
            self._write_quota(context, quota, account)

        removed = context.connection.execute(
            RETRACT_QUOTAS,
            {
                "tenant": unit.tenant_id,
                "account": account,
                "region": region,
                "run": context.run_id,
                "saw_global": any(quota.region_id is None for quota in quotas),
            },
        ).rowcount

        requests = tuple(self._source.requests(unit.account, region))
        for request in requests:
            self._write_request(context, request, account)

        self._record_advisor_gap(context, quotas, account, region, now)

        return CollectorOutcome(
            items_written=len(quotas) + len(requests),
            items_removed=max(removed, 0),
        )

    def _write_quota(self, context: CollectorContext, quota: QuotaUsage, account: str) -> None:
        context.connection.execute(
            WRITE_QUOTA,
            {
                "pk": uuid4(),
                "tenant": context.unit.tenant_id,
                "run": context.run_id,
                "account": account,
                "region": quota.region_id,
                "service": quota.service_code,
                "quota": quota.quota_code,
                "name": quota.quota_name,
                "limit": quota.quota_limit,
                "used": quota.used,
                "source": quota.usage_source.value,
                "reason": quota.unmeasurable_reason,
                "adjustable": quota.is_adjustable,
                # The provider's own two timestamps, not the clock. Constraint 10: `as_of` is
                # when the figure was true at the source and `collected_at` is when we read.
                "as_of": quota.as_of,
                "collected": quota.collected_at,
            },
        )

    def _write_request(
        self, context: CollectorContext, request: QuotaIncreaseRequest, account: str
    ) -> None:
        context.connection.execute(
            WRITE_REQUEST,
            {
                "pk": uuid4(),
                "tenant": context.unit.tenant_id,
                "run": context.run_id,
                "request": request.request_id,
                "account": account,
                "region": request.region_id,
                "service": request.service_code,
                "quota": request.quota_code,
                "desired": request.desired_value,
                "status": request.status.value,
                "requested": request.requested_at,
                "updated": request.last_updated_at,
                "as_of": request.as_of,
                "collected": request.collected_at,
            },
        )
        context.connection.execute(
            WRITE_HISTORY,
            {
                "pk": uuid4(),
                "tenant": context.unit.tenant_id,
                "request": request.request_id,
                "status": request.status.value,
                # AWS's timestamp for this transition, which is what lets a screen say when
                # a request was approved rather than only that it is.
                "changed": request.last_updated_at,
            },
        )

    def _record_advisor_gap(
        self,
        context: CollectorContext,
        quotas: tuple[QuotaUsage, ...],
        account: str,
        region: str,
        now: datetime,
    ) -> None:
        blocked = sum(
            1
            for quota in quotas
            if quota.usage_source is UsageSource.NONE
            and ADVISOR_MARKER in (quota.unmeasurable_reason or "")
        )
        if not blocked:
            return
        context.connection.execute(
            ADVISOR_GAP,
            {
                "id": uuid4(),
                "t": context.unit.tenant_id,
                "c": COLLECTOR,
                "s": f"{account}:{region}",
                "d": (
                    f"{blocked} quotas could only have been measured by Trusted Advisor, which "
                    "this account's support plan does not include"
                ),
                "r": (
                    "Trusted Advisor limit checks need Business or Enterprise support. Without "
                    "it these quotas show a limit and no usage, which is accurate: nothing "
                    "measured them. The rest of the estate is unaffected, and the ratio on the "
                    "quotas screen is the honest summary of the gap. OPEN-03."
                ),
                "now": now,
            },
        )
