"""The plans a pull request's pipeline would send, for the local stack's demo. P16, TASK-P16-009.

How a plan reaches Meter is OPEN-44, held by the owner, so the demo lays these down through
`record_plan`, the call the arrival route will make once TASK-P16-010 chooses it. They sit in the
fake estate's repository, in the two folders the demo maps to its Terraform states, and between
them reach every outcome a reader of the Estimates screen meets:

- 31, open: an older commit and the head, so the head's comment is written and the older one's is
  not, with a change priced from the catalog and one outside what P16 prices;
- 32, merged a hundred days before: created resources whose bills came within, above and below
  their estimates, and one never seen in its state;
- 33: its comment fails, as the fake host holds no such pull request, and neither change is priced,
  one in a Region the catalog lacks and one whose type is known only after apply;
- 34: a plan refused, as one that is not `terraform show -json` is;
- 35, merged the day before: a created resource seen and waiting for its thirty billed days;
- 36: a plan received and not yet priced.

The comparisons are laid down rather than computed, as P15's fix steps are: a verdict needs thirty
billed days after a merge, which a fresh demo does not have. Each figure is the judgement
`finops_query.estimate_accuracy.judge` gives for a bill at the stated share of the estimate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any, Final

from finops_fakes import fixtures
from finops_query.estimate_accuracy import Verdict
from finops_query.plan_reading import PlannedChange, ReducedPlan, Unreadable

#: The fake estate's Region, which the demo's catalog sells instances and volumes in.
REGION: Final = fixtures.REGION
#: A Region the catalog holds no price in.
UNPRICED_REGION: Final = "xx-none-1"
TERRAFORM: Final = "1.9.5"


@dataclass(frozen=True)
class DemoPlan:
    """One plan as its pipeline would send it, and when it arrived."""

    pull_request: int
    folder: str
    head_sha: str
    received_ago: timedelta
    found: ReducedPlan | Unreadable
    #: Priced by the demo's own run; a plan left out waits for the worker.
    priced: bool = True


@dataclass(frozen=True)
class DemoComparison:
    """What the bill said of one created resource: the bill's share of the estimate, or None."""

    pull_request: int
    address: str
    verdict: Verdict
    provider_id: str
    seen_ago: timedelta | None
    bill_share: Decimal | None = None


def created(
    address: str,
    resource_type: str,
    region: str = REGION,
    unknown: tuple[str, ...] = (),
    **after: Any,
) -> PlannedChange:
    return PlannedChange(address, resource_type, ("create",), region, {}, after, unknown=unknown)


def plan(*changes: PlannedChange) -> ReducedPlan:
    return ReducedPlan("1.2", TERRAFORM, None, changes)


def _gp3(size: int) -> dict[str, Any]:
    return {"type": "gp3", "size": size}


DEMO_PLANS: Final[tuple[DemoPlan, ...]] = (
    DemoPlan(
        31,
        "platform",
        "a1b2c3d4e5f6",
        timedelta(hours=3),
        plan(created("aws_instance.web", "aws_instance", instance_type="t3.medium")),
    ),
    DemoPlan(
        31,
        "platform",
        "b2c3d4e5f6a7",
        timedelta(hours=2),
        plan(
            created("aws_instance.web", "aws_instance", instance_type="m5.large"),
            created("aws_ebs_volume.data", "aws_ebs_volume", **_gp3(100)),
            created("aws_nat_gateway.out", "aws_nat_gateway"),
        ),
    ),
    DemoPlan(
        32,
        "network",
        "c3d4e5f6a7b8",
        timedelta(days=101),
        plan(
            created("aws_instance.api", "aws_instance", instance_type="m5.large"),
            created("aws_instance.batch", "aws_instance", instance_type="t3.large"),
            created("aws_ebs_volume.logs", "aws_ebs_volume", **_gp3(200)),
            created("aws_instance.gone", "aws_instance", instance_type="t3.small"),
        ),
    ),
    DemoPlan(
        33,
        "platform",
        "d4e5f6a7b8c9",
        timedelta(hours=5),
        plan(
            created("aws_instance.edge", "aws_instance", UNPRICED_REGION, instance_type="t3.small"),
            created("aws_instance.cache", "aws_instance", unknown=("instance_type",)),
        ),
    ),
    DemoPlan(
        34,
        "network",
        "e5f6a7b8c9d0",
        timedelta(hours=4),
        Unreadable("the file is not the JSON that terraform show -json writes"),
    ),
    DemoPlan(
        35,
        "platform",
        "f6a7b8c9d0e1",
        timedelta(days=2),
        plan(created("aws_instance.queue", "aws_instance", instance_type="m5.large")),
    ),
    DemoPlan(
        36,
        "network",
        "0a1b2c3d4e5f",
        timedelta(minutes=5),
        plan(created("aws_ebs_volume.scratch", "aws_ebs_volume", **_gp3(50))),
        priced=False,
    ),
)

#: The pull requests the fake host holds, each with its head and whether it merged. Pull request
#: 33 is not among them, so its comment fails.
DEMO_HEADS: Final[dict[int, tuple[str, bool]]] = {
    31: ("b2c3d4e5f6a7", False),
    32: ("c3d4e5f6a7b8", True),
    35: ("f6a7b8c9d0e1", True),
}
#: How long before the seed Meter first saw each merged pull request merged.
DEMO_MERGED_AGO: Final[dict[int, timedelta]] = {32: timedelta(days=100), 35: timedelta(days=1)}

DEMO_COMPARISONS: Final[tuple[DemoComparison, ...]] = (
    DemoComparison(
        32,
        "aws_instance.api",
        Verdict.WITHIN,
        "i-0demo0api0000001",
        timedelta(days=99),
        Decimal("1.04"),
    ),
    DemoComparison(
        32,
        "aws_instance.batch",
        Verdict.ABOVE,
        "i-0demo0batch00001",
        timedelta(days=99),
        Decimal("1.27"),
    ),
    DemoComparison(
        32,
        "aws_ebs_volume.logs",
        Verdict.BELOW,
        "vol-0demo0logs0001",
        timedelta(days=99),
        Decimal("0.74"),
    ),
    DemoComparison(32, "aws_instance.gone", Verdict.NOT_COMPARED, "i-0demo0gone00001", None),
    DemoComparison(
        35, "aws_instance.queue", Verdict.PENDING, "i-0demo0queue0001", timedelta(hours=12)
    ),
)
#: What commitments take off a judged resource's list cost, so effective cost sits apart from it.
EFFECTIVE_SHARE: Final = Decimal("0.72")
