"""The burstable instance types' baselines, from the EC2 guide's credit table. TASK-P9-005.

P9 spec section 5.4: `DescribeInstanceTypes` says a type is burstable and says nothing of the
baseline it earns credits at, so the figure is the guide's, kept here as data with its source.
A burstable type this table does not list is never given a baseline by guess: the collector
records it as NoData and stores nothing for it, and `tests/providers/aws/test_burstable.py` fails
when a type the estate or a real description names is missing.

Each row is the guide's: credits earned an hour, the most that can be accrued, vCPUs, and the
baseline per vCPU, which is the CPU utilisation CloudWatch shows when the instance runs at its
baseline (30 percent for a t3.large). The table checks itself on import: credits earned are the
baseline times the vCPUs times 60 minutes, and the accrual limit is 24 hours of them, the two
formulas the guide states, so a figure copied wrongly fails before anything reads it.

The managed services' burstable classes, `db.t3.micro` and `cache.t4g.small`, are read as the EC2
type of the same family and size. AWS documents those classes as burstable but publishes no table
of its own for them, so the baseline is the EC2 row's and its source says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

#: The guide's page, cited beside every stored baseline and never fetched.
_GUIDE_SITE: Final = "https://docs.aws.amazon.com"  # allow-hardcoded: cited, never fetched
_GUIDE_PAGE: Final = "/AWSEC2/latest/UserGuide/burstable-credits-baseline-concepts.html"
#: The page and the day it was read. Every stored baseline names it.
SOURCE: Final = (
    "EC2 User Guide, Key concepts for burstable performance instances, credit table, "
    f"{_GUIDE_SITE}{_GUIDE_PAGE}, read 2026-10-08"
)
#: The burstable families, from the same page.
FAMILIES: Final = frozenset({"t2", "t3", "t3a", "t4g", "t8i"})
#: The prefixes and suffixes a managed service puts around an EC2 type's name.
_PREFIXES: Final = ("db.", "cache.")
_SUFFIXES: Final = (".search", ".elasticsearch")


@dataclass(frozen=True)
class Baseline:
    credits_per_hour: Decimal
    maximum_credits: Decimal
    vcpus: int
    #: The baseline per vCPU, as a share: 0.30 for 30 percent.
    per_vcpu: Decimal


def _row(earned: str, maximum: str, vcpus: int, percent: str) -> Baseline:
    return Baseline(Decimal(earned), Decimal(maximum), vcpus, Decimal(percent) / 100)


#: Every row of the guide's table, as read on 2026-10-08.
TABLE: Final[dict[str, Baseline]] = {
    "t8i.nano": _row("6", "144", 2, "5"),
    "t8i.micro": _row("12", "288", 2, "10"),
    "t8i.small": _row("24", "576", 2, "20"),
    "t8i.medium": _row("24", "576", 2, "20"),
    "t4g.nano": _row("6", "144", 2, "5"),
    "t4g.micro": _row("12", "288", 2, "10"),
    "t4g.small": _row("24", "576", 2, "20"),
    "t4g.medium": _row("24", "576", 2, "20"),
    "t4g.large": _row("36", "864", 2, "30"),
    "t4g.xlarge": _row("96", "2304", 4, "40"),
    "t4g.2xlarge": _row("192", "4608", 8, "40"),
    "t3a.nano": _row("6", "144", 2, "5"),
    "t3a.micro": _row("12", "288", 2, "10"),
    "t3a.small": _row("24", "576", 2, "20"),
    "t3a.medium": _row("24", "576", 2, "20"),
    "t3a.large": _row("36", "864", 2, "30"),
    "t3a.xlarge": _row("96", "2304", 4, "40"),
    "t3a.2xlarge": _row("192", "4608", 8, "40"),
    "t3.nano": _row("6", "144", 2, "5"),
    "t3.micro": _row("12", "288", 2, "10"),
    "t3.small": _row("24", "576", 2, "20"),
    "t3.medium": _row("24", "576", 2, "20"),
    "t3.large": _row("36", "864", 2, "30"),
    "t3.xlarge": _row("96", "2304", 4, "40"),
    "t3.2xlarge": _row("192", "4608", 8, "40"),
    "t2.nano": _row("3", "72", 1, "5"),
    "t2.micro": _row("6", "144", 1, "10"),
    "t2.small": _row("12", "288", 1, "20"),
    "t2.medium": _row("24", "576", 2, "20"),
    "t2.large": _row("36", "864", 2, "30"),
    "t2.xlarge": _row("54", "1296", 4, "22.5"),
    "t2.2xlarge": _row("81.6", "1958.4", 8, "17"),
}


def _check(table: dict[str, Baseline]) -> None:
    for name, row in table.items():
        earned = row.per_vcpu * row.vcpus * 60
        if earned != row.credits_per_hour or row.credits_per_hour * 24 != row.maximum_credits:
            raise ValueError(f"{name}'s row does not follow the guide's own formulas")


_check(TABLE)


def counterpart(instance_type: str) -> str:
    """The EC2 type a managed service's class is named after: `db.t3.micro` is `t3.micro`."""
    name = instance_type
    for prefix in _PREFIXES:
        name = name.removeprefix(prefix)
    for suffix in _SUFFIXES:
        name = name.removesuffix(suffix)
    return name


def is_burstable_name(instance_type: str) -> bool:
    """Whether a type's family is one of the burstable ones, by its name."""
    return counterpart(instance_type).split(".")[0] in FAMILIES


def baseline_of(instance_type: str) -> tuple[Baseline, str] | None:
    """The guide's row for a type, with the source to store beside it. None if it has none."""
    ec2 = counterpart(instance_type)
    row = TABLE.get(ec2)
    if row is None:
        return None
    source = SOURCE if ec2 == instance_type else f"{SOURCE}, the row for {ec2}"
    return row, source
