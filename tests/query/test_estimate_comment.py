"""An estimate as its pull request's one comment. TASK-P16-006, FEAT-096, spec section 5.5.

The unpriced count comes first, then the figures, a line per priced resource, every one not priced
with its reason, the notes, and what every figure rests on; list prices only, never the bill. The
comment opens with the folder's marker and never outgrows what GitHub accepts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from finops_query.estimate_comment import (
    LISTED,
    MOST,
    CommentedEstimate,
    CommentLine,
    marker,
    render,
)

AT = datetime(2026, 10, 16, 9, 5, tzinfo=UTC)
WEB = CommentLine(
    "aws_instance.web",
    ("create",),
    None,
    Decimal("82.51"),
    notes=("priced as Linux: the image's platform is not in the plan",),
)
OLD = CommentLine("aws_ebs_volume.old", ("delete",), Decimal("8.8"), None)
NAT = CommentLine(
    "aws_nat_gateway.out",
    ("create",),
    None,
    None,
    reason="aws_nat_gateway is billed by use, which a plan does not say",
)


def estimate(
    *lines: CommentLine, versions: tuple[str, ...] = ("20261001000000",)
) -> CommentedEstimate:
    before = sum((one.monthly_before or Decimal(0) for one in lines), Decimal(0))
    after = sum((one.monthly_after or Decimal(0) for one in lines), Decimal(0))
    return CommentedEstimate(
        folder="storage",
        head_sha="abc1234def567890",
        monthly_before=before,
        monthly_after=after,
        monthly_change=after - before,
        lines=lines,
        versions=versions,
        priced_at=AT,
    )


def test_the_comment_opens_with_its_folders_marker_and_says_what_is_not_priced_first() -> None:
    body = render(estimate(WEB, OLD, NAT))
    lines = body.splitlines()
    assert lines[0] == marker("storage") == "<!-- meter:estimate folder=storage -->"
    assert lines[3].startswith("**1 of 3 resources is not priced**, so the figures below leave it")
    assert "| 8.80 USD | 82.51 USD | **+73.71 USD** |" in body
    assert body.index("not priced") < body.index("| Resource |")


def test_each_priced_resource_is_a_row_and_each_unpriced_one_a_reason() -> None:
    body = render(estimate(WEB, OLD, NAT))
    assert "| `aws_instance.web` | create |  | 82.51 | +82.51 |" in body
    assert "| `aws_ebs_volume.old` | destroy | 8.80 |  | -8.80 |" in body
    assert "- `aws_nat_gateway.out`: aws_nat_gateway is billed by use" in body
    assert "<summary>Notes</summary>" in body
    assert "- `aws_instance.web`: priced as Linux" in body


def test_the_footing_says_what_every_figure_rests_on_and_never_the_bill() -> None:
    body = render(estimate(WEB, versions=("20261001000000", "20261006224050")))
    assert body.rstrip().endswith(
        "Modelled from AWS's on demand list prices, 730 hours a month, in USD, price list versions "
        "20261001000000, 20261006224050. Commitment discounts are not applied. Commit "
        "`abc1234def56`, priced 2026-10-16 09:05 UTC."
    )
    assert "bill" not in body.lower()


def test_a_plan_all_priced_and_one_changing_nothing_say_so() -> None:
    assert "Every one of the 2 resources this plan changes is priced." in render(estimate(WEB, OLD))
    empty = render(estimate(versions=()))
    assert "This plan changes nothing Meter prices." in empty
    assert "price list version none read" in empty
    assert "| Resource |" not in empty


def test_a_replacement_and_a_change_read_as_such_and_a_pipe_cannot_break_the_table() -> None:
    swapped = CommentLine(
        'aws_ebs_volume.v["a|b"]', ("delete", "create"), Decimal("11"), Decimal("8.8")
    )
    resized = CommentLine("aws_instance.app", ("update",), Decimal("78.11"), Decimal("156.22"))
    body = render(estimate(swapped, resized))
    assert '| `aws_ebs_volume.v["a\\|b"]` | replace | 11.00 | 8.80 | -2.20 |' in body
    assert "| `aws_instance.app` | change | 78.11 | 156.22 | +78.11 |" in body


def test_a_plan_too_large_to_list_is_counted_and_cut_short_of_githubs_limit() -> None:
    many = tuple(
        CommentLine(f"aws_instance.n{index}", ("create",), None, Decimal("1"))
        for index in range(250)
    )
    body = render(estimate(*many))
    assert f"- and {250 - LISTED} more, on Meter's Estimates screen" in body
    long_reason = "x" * 400
    huge = tuple(
        CommentLine(f"aws_s3_bucket.b{index}", ("create",), None, None, reason=long_reason)
        for index in range(LISTED)
    )
    cut = render(estimate(*huge))
    assert len(cut) <= MOST
    assert cut.endswith("The rest is on Meter's Estimates screen.\n")
