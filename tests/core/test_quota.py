"""A quota nobody measures has unknown headroom, and unknown is not a number.

The four rules TASK-P5-001 asks for, and the two absences they are really about. A
quota carries two figures that can each be missing for an honest reason: AWS publishes
usage for a minority of quotas, and publishes no limit for a few. Neither absence is a
zero, and the whole of P5 is downstream of that.

The tests that matter here are the ones asserting a value **cannot** be constructed.
`headroom` returning None is easy to write and easy to undo later while every rendering
assertion still passes; a `ValueError` raised in `__post_init__` fails at the line that
caused it. The same rules are database constraints in 0020, per constraint 11, and
`tests/db/test_p5_constraints.py` watches them from that side.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.fact import Fact
from finops_core.domain.quota import QuotaUsage, UsageSource

NOW = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)
KEY = AccountKey(provider=Provider.AWS, account_id="111111111111")


def quota(
    *,
    limit: Decimal | None = Decimal("100"),
    used: Decimal | None = Decimal("40"),
    source: UsageSource = UsageSource.AWS_USAGE_METRIC,
    region: str | None = "eu-west-1",
    adjustable: bool = True,
) -> QuotaUsage:
    """A measurable quota at 40 of 100, which every test here varies one field of."""
    return QuotaUsage(
        account_key=KEY,
        region_id=region,
        service_code="ec2",
        quota_code="L-1216C47A",
        quota_name="Running On-Demand Standard instances",
        quota_limit=limit,
        used=used,
        usage_source=source,
        is_adjustable=adjustable,
        as_of=NOW,
        collected_at=NOW,
    )


def test_inherits_fact_so_it_cannot_lose_its_timestamps() -> None:
    """Constraints 4 and 10, inherited rather than repeated. TASK-P5-001."""
    assert issubclass(QuotaUsage, Fact)
    fields = {f.name for f in dataclasses.fields(QuotaUsage)}
    assert {"as_of", "collected_at"} <= fields


def test_headroom_is_the_fraction_free_where_it_is_measured() -> None:
    """The ordinary case, so the None cases below are read as exceptions to something."""
    assert quota(limit=Decimal("100"), used=Decimal("40")).headroom == Decimal("0.6")


def test_headroom_is_none_where_nothing_measured_the_usage() -> None:
    """Not 1 and not 0. Both would be claims, and neither is known. TASK-P5-001."""
    unmeasured = quota(used=None, source=UsageSource.NONE)
    assert unmeasured.headroom is None
    assert unmeasured.is_measurable is False


def test_headroom_is_none_where_the_provider_published_no_limit() -> None:
    """The second absence. A quota whose ceiling nobody states has no fraction free."""
    assert quota(limit=None).headroom is None


def test_headroom_is_none_at_a_limit_of_zero_rather_than_dividing_by_it() -> None:
    """A limit of zero is a real value meaning the thing is switched off here.

    It is not refused, because refusing it would lose a real quota. It has no fraction
    free, because the fraction free of nothing is not a number anybody can sort by, and
    a screen sorting by headroom is exactly what this property feeds.
    """
    assert quota(limit=Decimal("0"), used=None, source=UsageSource.NONE).headroom is None


def test_a_usage_figure_with_no_source_cannot_be_constructed() -> None:
    """The first half of the biconditional. A figure with no provenance cannot be audited.

    It also renders identically to one that was measured, which is why the rule is here
    and not only in a repository. TASK-P5-001, and spec section 5.1.
    """
    with pytest.raises(ValueError, match="move together"):
        quota(used=Decimal("40"), source=UsageSource.NONE)


def test_a_source_with_no_usage_figure_cannot_be_constructed() -> None:
    """The other half, and the one a test is likely to forget.

    A source naming Trusted Advisor beside no figure claims a measurement nobody made,
    and it would put the quota in the measurable list with nothing to show.
    """
    with pytest.raises(ValueError, match="move together"):
        quota(used=None, source=UsageSource.TRUSTED_ADVISOR)


def test_a_usage_above_the_limit_cannot_be_constructed() -> None:
    """A quota is the ceiling, so this is a misread rather than an estate in trouble.

    Rendering it would draw headroom below zero and rank it above every real problem.
    TASK-P5-001.
    """
    with pytest.raises(ValueError, match="exceeds the limit"):
        quota(limit=Decimal("100"), used=Decimal("101"))


def test_a_usage_equal_to_the_limit_is_allowed_because_it_happens() -> None:
    """The boundary the check above must not take with it: a full quota is the finding."""
    full = quota(limit=Decimal("100"), used=Decimal("100"))
    assert full.headroom == Decimal("0")


def test_a_usage_above_an_unpublished_limit_is_not_refused() -> None:
    """Spec 5.1 constrains the pair only where both are present.

    Nothing is known about the ceiling, so nothing about the figure contradicts it. The
    alternative is discarding a measured usage because the limit was missing.
    """
    assert quota(limit=None, used=Decimal("5000")).used == Decimal("5000")


def test_a_negative_limit_cannot_be_constructed() -> None:
    """Zero is switched off and a negative is a misread. Spec 5.1 says at or above zero."""
    with pytest.raises(ValueError, match="below zero"):
        quota(limit=Decimal("-1"), used=None, source=UsageSource.NONE)


def test_a_global_quota_carries_no_region_rather_than_a_placeholder() -> None:
    """IAM roles per account are counted once, not once per region.

    A placeholder region would let a screen show the same limit five times and add them
    up. Distinct from a region nobody could read, which is a typed failure.
    """
    assert quota(region=None).region_id is None


def test_is_measurable_reads_the_source_and_not_the_figure() -> None:
    """The predicate the two lists are split on, over all four sources."""
    for source in (
        UsageSource.AWS_USAGE_METRIC,
        UsageSource.TRUSTED_ADVISOR,
        UsageSource.SERVICE_API,
    ):
        assert quota(source=source).is_measurable is True
    assert quota(used=None, source=UsageSource.NONE).is_measurable is False


def test_the_source_vocabulary_is_exactly_the_four_the_spec_names() -> None:
    """A fifth source is a schema change, not a convenience.

    The vocabulary is stored in a column with a check constraint, mirrored by the fake
    estate and rendered by a screen, so a member added here without the rest is a row
    the database refuses or a label the screen has not got. ADR-0026 is the record of
    what that costs when it happens to the cause vocabulary instead.
    """
    assert {s.value for s in UsageSource} == {
        "AWS_USAGE_METRIC",
        "TRUSTED_ADVISOR",
        "SERVICE_API",
        "NONE",
    }


def test_a_quota_is_frozen() -> None:
    """A fact that can be edited after the fact is not one."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        quota().used = Decimal("1")  # type: ignore[misc]
