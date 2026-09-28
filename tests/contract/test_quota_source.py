"""One contract for reading quotas, held by the fake and by AWS Service Quotas.

The sentences here are P5 spec section 5.2 turned into a requirement, and they belong in a
contract rather than in one adapter's tests because the failure they prevent is silent in
both implementations. A source that returned only the quotas it could measure would pass
every test about measured quotas, and the screen built on it would report an estate with
excellent headroom everywhere.

Five sentences:

1. Every quota the provider knows about comes back, measured or not.
2. An unmeasured quota carries a null usage and never a zero.
3. An unmeasured quota says why, in a sentence.
4. A measured quota names where its figure came from, and carries no reason.
5. An increase request is readable whatever became of it, including refused, and including
   for a quota nothing can measure.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from finops_core.domain.quota import QuotaIncreaseRequest, QuotaUsage, UsageSource
from finops_core.ports.quotas import QuotaSource
from tests.contract.conftest import QUOTA_SOURCE, ProviderUnderTest

Requires = Callable[[str], None]


def test_the_source_satisfies_the_port(subject: ProviderUnderTest, requires_port: Requires) -> None:
    requires_port(QUOTA_SOURCE)
    assert isinstance(subject.provider, QuotaSource)


def test_both_measured_and_unmeasured_quotas_come_back(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """The sentence the whole sub project rests on.

    A source returning only what it could measure is the failure mode here, and it is
    invisible to any test that looks only at the rows it did return.
    """
    requires_port(QUOTA_SOURCE)
    quotas = tuple(subject.provider.list_quotas(subject.known_account, subject.region))
    assert quotas, "a readable account with no quotas is not an account this contract can judge"
    assert all(isinstance(one, QuotaUsage) for one in quotas)

    measurable = [one for one in quotas if one.is_measurable]
    unmeasurable = [one for one in quotas if not one.is_measurable]
    assert measurable, "no measured quota, so nothing here proves a figure ever arrives"
    assert unmeasurable, "no unmeasured quota, so the null path is the one nobody exercises"


def test_an_unmeasured_quota_is_null_and_never_zero(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """Zero would read as plenty of headroom on a quota nobody has measured."""
    requires_port(QUOTA_SOURCE)
    for one in subject.provider.list_quotas(subject.known_account, subject.region):
        if one.is_measurable:
            continue
        assert one.used is None, f"{one.quota_code} reports a usage with no source"
        assert one.usage_source is UsageSource.NONE
        assert one.headroom is None, f"{one.quota_code} claims headroom nobody measured"


def test_an_unmeasured_quota_says_why(subject: ProviderUnderTest, requires_port: Requires) -> None:
    """A blank reason in the second list teaches a reader the explanations are empty."""
    requires_port(QUOTA_SOURCE)
    for one in subject.provider.list_quotas(subject.known_account, subject.region):
        if one.is_measurable:
            continue
        reason = (one.unmeasurable_reason or "").strip()
        assert reason, f"{one.quota_code} is unmeasurable and does not say why"
        # Not a length assertion: the entity already enforces the floor. This is about the
        # sentence reading as one rather than as a token somebody reused.
        assert reason[0].isupper(), f"{one.quota_code} reason is not written as a sentence"


def test_a_measured_quota_names_its_source_and_carries_no_reason(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """A reason surviving the day a quota starts publishing usage is the rot to prevent."""
    requires_port(QUOTA_SOURCE)
    for one in subject.provider.list_quotas(subject.known_account, subject.region):
        if not one.is_measurable:
            continue
        assert one.used is not None
        assert one.usage_source in (
            UsageSource.AWS_USAGE_METRIC,
            UsageSource.TRUSTED_ADVISOR,
            UsageSource.SERVICE_API,
        )
        assert one.unmeasurable_reason is None, f"{one.quota_code} is measured and explains why not"


def test_a_measured_usage_never_exceeds_its_own_limit(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """Held by the entity, and asserted here because the entity is what both share.

    A source that clamped instead of refusing would satisfy the entity and hide a misread,
    so the contract asks the question of the values that came back.
    """
    requires_port(QUOTA_SOURCE)
    for one in subject.provider.list_quotas(subject.known_account, subject.region):
        if one.used is None or one.quota_limit is None:
            continue
        assert one.used <= one.quota_limit, f"{one.quota_code} reports more used than it has"


def test_a_global_quota_carries_no_region(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """Otherwise a screen shows one account level limit once per region and sums them."""
    requires_port(QUOTA_SOURCE)
    quotas = tuple(subject.provider.list_quotas(subject.known_account, subject.region))
    assert {one.region_id for one in quotas} <= {subject.region, None}


def test_requests_are_readable_whatever_became_of_them(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """Including refused, which is the status a product is tempted to hide.

    FEAT-034 exists for the increase nobody checked on, so a tracking list showing only the
    open ones would drop exactly the answer somebody was waiting for.
    """
    requires_port(QUOTA_SOURCE)
    requests = tuple(subject.provider.requests(subject.known_account, subject.region))
    assert requests, "no requests at all, so nothing here proves the history is read"
    assert all(isinstance(one, QuotaIncreaseRequest) for one in requests)
    assert any(not one.status.is_open for one in requests), (
        "every request is still open, so the settled path is the one nobody exercises"
    )
    for one in requests:
        assert one.desired_value > Decimal(0)
        assert one.last_updated_at >= one.requested_at


def test_a_request_is_tracked_even_where_the_quota_cannot_be_measured(
    subject: ProviderUnderTest, requires_port: Requires
) -> None:
    """Tracking and measuring are independent, which is the whole of TASK-P5-008.

    A product that tracked only what it could measure would lose the requests somebody made
    precisely because they had no figure to look at.
    """
    requires_port(QUOTA_SOURCE)
    unmeasurable = {
        one.quota_code
        for one in subject.provider.list_quotas(subject.known_account, subject.region)
        if not one.is_measurable
    }
    tracked = {
        one.quota_code for one in subject.provider.requests(subject.known_account, subject.region)
    }
    assert unmeasurable & tracked, (
        "no request names an unmeasurable quota, so the independence of the two is untested"
    )
