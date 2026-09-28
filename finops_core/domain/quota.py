"""One service quota, how much of it is in use, and any increase asked for.

`used` is optional because a quota whose usage the provider does not publish is
a real and common case. It is None rather than zero, because zero would read as
plenty of headroom on a quota that is in fact about to be hit.

P5 widened this and added almost nothing, which the implementation plan predicted
and called worth noticing: P0 had already made the decision this whole sub project
is downstream of, that unpublished usage is an absence rather than a number. What
P5 adds is provenance for the figure, because a usage of 40 read from a CloudWatch
metric and a usage of 40 read from Trusted Advisor are not equally trustworthy,
and a figure with no recorded source cannot be audited a year later.

**The source names are AWS shaped, in a module that imports no cloud.** That is
deliberate and it is the lesser of two wrongs. The vocabulary is fixed by the P5
spec's section 5.1, it is stored in a database column, it is mirrored by the fake
estate and it will be rendered by a screen. A provider neutral synonym invented
here would be a fifth spelling of the same four things, and ADR-0026 is the record
of what mirrored vocabularies cost when one copy drifts. Constraint 1 forbids the
SDK, not the knowledge of what the SDK returns.

**The request statuses were read out of the service model, not out of the spec.**
The P5 spec names five and `RequestStatus` in botocore has seven. See the enum.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from finops_core.domain.account import AccountKey
from finops_core.domain.fact import Fact


class UsageSource(StrEnum):
    """Where a usage figure came from, or that there is none.

    Three sources and an absence, and the absence is a member rather than a null
    beside the enum, because `NONE` is the common case rather than the exceptional
    one. AWS publishes usage for a minority of its quotas, and a design that treated
    that as the error path would be describing a different cloud.
    """

    #: A CloudWatch metric in the `AWS/Usage` namespace. The largest source and the
    #: one with the fewest caveats: it is the service reporting its own consumption.
    AWS_USAGE_METRIC = "AWS_USAGE_METRIC"
    #: A Trusted Advisor limit check. Needs Business or Enterprise support, so on a
    #: Developer plan this source contributes nothing and the measurable list is
    #: simply shorter. OPEN-03, and it reduces coverage rather than raising.
    TRUSTED_ADVISOR = "TRUSTED_ADVISOR"
    #: A service's own API, counted by us. `DescribeVpcs` and the like, for the few
    #: quotas where the count is one call away and nothing else publishes it.
    SERVICE_API = "SERVICE_API"
    #: Nothing measures this quota. Not a failure, and not zero: a fact about what
    #: AWS publishes, and the reason this product shows two lists instead of one.
    NONE = "NONE"


@dataclass(frozen=True, kw_only=True)
class QuotaUsage(Fact):
    """One quota for one account, in one region or across all of them."""

    account_key: AccountKey
    #: None where the quota is global rather than regional. IAM roles per account,
    #: S3 buckets per account and CloudFront distributions are counted once for the
    #: whole account, and putting a region on one of those would invite a screen to
    #: show the same limit once per region and a total of five times the truth.
    #: Distinct from a region nobody could read, which is a typed failure.
    region_id: str | None
    service_code: str
    quota_code: str
    quota_name: str
    #: None where the provider publishes no limit for the quota. The same absence as
    #: `used` and for the same reason: a quota whose ceiling nobody states does not
    #: have a ceiling of nothing. Zero is a real and different value, meaning the
    #: thing is switched off here.
    quota_limit: Decimal | None
    #: None where the provider publishes no usage. Never zero as a stand in.
    used: Decimal | None
    #: Where `used` came from, or `NONE`. The two move together and `__post_init__`
    #: refuses any other combination.
    usage_source: UsageSource = UsageSource.NONE
    #: Whether an increase can be requested at all. A hard limit cannot be raised,
    #: and drafting a request against one wastes somebody's afternoon: FEAT-034 has
    #: to know which it is before it offers a draft.
    is_adjustable: bool = True

    def __post_init__(self) -> None:
        """Refuse the three combinations that would be lies.

        All three are also database constraints, and the duplication is deliberate:
        constraint 11 says application code is not what should prevent a bad row, and
        this is what stops one being constructed in the first place, so the failure
        arrives at the line that caused it rather than at the commit.
        """
        if (self.used is None) != (self.usage_source is UsageSource.NONE):
            raise ValueError(
                f"usage and its source move together: used={self.used!r} with "
                f"usage_source={self.usage_source!r}. A figure with no source cannot be "
                f"audited later, and a source with no figure claims a measurement nobody made."
            )
        if self.quota_limit is not None and self.quota_limit < 0:
            raise ValueError(
                f"the limit {self.quota_limit} for {self.quota_code} is below zero. Zero is "
                f"a real limit and means the thing is switched off here; a negative one is "
                f"a misread, and it would draw as headroom on the wrong side of the track."
            )
        if self.used is not None and self.quota_limit is not None and self.used > self.quota_limit:
            raise ValueError(
                f"used {self.used} exceeds the limit {self.quota_limit} for "
                f"{self.quota_code}. A quota is the ceiling, so this is a misread rather "
                f"than an estate in trouble, and rendering it would show headroom below zero."
            )

    @property
    def headroom(self) -> Decimal | None:
        """The fraction of the quota still free, or None where it is not a number.

        None and never a fraction, which is the whole entity in one property. A quota
        nobody measures has unknown headroom, and returning 1 would say it is entirely
        free while returning 0 would say it is exhausted. Both are claims, and neither
        is known.

        An unpublished limit and a limit of zero both yield None as well, for the same
        reason rather than by raising: in the first the ceiling is unknown, and in the
        second the quota is switched off, so the fraction free is in neither case a
        number anybody can act on or sort by.
        """
        if self.used is None or self.quota_limit is None or self.quota_limit <= 0:
            return None
        return (self.quota_limit - self.used) / self.quota_limit

    @property
    def is_measurable(self) -> bool:
        """Whether anything at all reports consumption for this quota.

        The predicate the two lists are split on. It reads `usage_source` rather than
        `used`, because the two are held equal by `__post_init__` and the source is the
        fact being asserted: this is a statement about what AWS publishes, not about
        how this one reading happened to come out.
        """
        return self.usage_source is not UsageSource.NONE


class RequestStatus(StrEnum):
    """Where an increase request has got to. AWS's vocabulary, not ours to improve.

    **Seven, and the P5 spec says five.** The spec's section 5.3 lists PENDING,
    CASE_OPENED, APPROVED, DENIED and CASE_CLOSED. The `RequestStatus` shape in the
    botocore service model, which is the model boto3 builds its own client from, also
    has NOT_APPROVED and INVALID_REQUEST. The spec was written from the documentation
    and the two extra values were missed.

    Found at TASK-P5-003 by adding the operation to `tests/providers/aws/
    test_response_shapes.py` before writing the adapter, which is the only reason it
    was found before a real account rather than after. Had the narrower vocabulary
    shipped, a request in either state would have been read successfully, refused by a
    check constraint, and reported as a collector fault.
    """

    PENDING = "PENDING"
    CASE_OPENED = "CASE_OPENED"
    APPROVED = "APPROVED"
    #: Refused, with a reason a person gave.
    DENIED = "DENIED"
    CASE_CLOSED = "CASE_CLOSED"
    #: Also refused, and distinct from DENIED in AWS's own model. Kept separate rather
    #: than folded in, because collapsing two of somebody else's values into one of ours
    #: is how a vocabulary stops being theirs and starts being a guess.
    NOT_APPROVED = "NOT_APPROVED"
    #: The request itself was malformed, so nobody ever considered it. Worth showing: it
    #: is the one state where the thing to do is ask again rather than wait.
    INVALID_REQUEST = "INVALID_REQUEST"

    @property
    def is_open(self) -> bool:
        """Whether this request is still going somewhere.

        The predicate the tracking list is built on, and the reason FEAT-034 exists:
        nobody loses a quota increase for want of the button, they lose it because
        nobody checked whether it was ever approved.
        """
        return self in (RequestStatus.PENDING, RequestStatus.CASE_OPENED)


@dataclass(frozen=True, kw_only=True)
class QuotaIncreaseRequest(Fact):
    """An increase somebody asked AWS for. Read, and never written.

    Constraint 6 and P5 spec section 6: `RequestServiceQuotaIncrease` is a write into a
    member account, so Meter drafts a request, hands it to a person, and then reads this
    back to say what became of it. The entity has no constructor that could submit one
    and the schema has a column that can only say false.
    """

    account_key: AccountKey
    #: AWS's own request id, which is what makes a re read an update rather than a second
    #: row. Never ours: Meter did not create this request and has nothing to name it with.
    request_id: str
    #: None where the quota is global, as on `QuotaUsage` and for the same reason.
    region_id: str | None
    service_code: str
    quota_code: str
    quota_name: str
    desired_value: Decimal
    status: RequestStatus
    #: AWS's timestamps for the request, distinct from the pair `Fact` carries for our
    #: read of it. Constraint 10 is about the second pair; these two are the subject.
    requested_at: datetime
    last_updated_at: datetime

    def __post_init__(self) -> None:
        """Refuse a request that asks for nothing, or that moved before it existed."""
        if self.desired_value <= 0:
            raise ValueError(
                f"request {self.request_id} asks for {self.desired_value}, which is not an "
                f"increase. A draft against this would suggest lowering a limit."
            )
        if self.last_updated_at < self.requested_at:
            raise ValueError(
                f"request {self.request_id} was last updated {self.last_updated_at} before it "
                f"was made at {self.requested_at}, so one of the two is a misread."
            )
