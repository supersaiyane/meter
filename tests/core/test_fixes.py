"""Which fixes Meter may merge, and when. ADR-0038, FEAT-094, TASK-P15-001.

The rule says no, with the reason, for each thing that must be true, and yes only when every one
is: merging on, a reversible class, named by the policy, opened by Meter, still open, and ready by
the repository's own checks and reviews.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from finops_core.domain.fixes import REVERSIBLE, PullRequestState, Readiness, may_merge
from finops_core.domain.waste import WasteClass

GP3 = WasteClass.EBS_GP2_TO_GP3
READY = PullRequestState(
    number=7,
    url="https://code.example/acme/infra/pull/7",
    open=True,
    merged=False,
    readiness=Readiness.READY,
    head_sha="head-7",
)


def verdict(**changes: object) -> tuple[bool, str]:
    arguments: dict[str, object] = {
        "waste_class": GP3,
        "allowed_classes": frozenset({GP3}),
        "opened_by_meter": True,
        "state": READY,
        "merging_on": True,
    }
    arguments.update(changes)
    found = may_merge(**arguments)  # type: ignore[arg-type]
    return found.allowed, found.reason


def test_the_reversible_set_is_gp2_to_gp3_alone() -> None:
    """Adding to it is a change to ADR-0038, so a test names its whole contents."""
    assert frozenset({GP3}) == REVERSIBLE


def test_a_ready_reversible_fix_the_policy_names_may_be_merged() -> None:
    allowed, reason = verdict()
    assert allowed is True
    assert "required checks and reviews have passed" in reason


@pytest.mark.parametrize(
    ("changes", "says"),
    [
        ({"merging_on": False}, "turned off"),
        ({"waste_class": WasteClass.EBS_UNATTACHED}, "not reversible"),
        ({"allowed_classes": frozenset()}, "does not name"),
        ({"opened_by_meter": False}, "only a pull request it opened"),
        ({"state": replace(READY, merged=True)}, "already merged"),
        ({"state": replace(READY, open=False)}, "closed without merging"),
        ({"state": replace(READY, readiness=Readiness.WAITING)}, "not all passed yet"),
        ({"state": replace(READY, readiness=Readiness.BLOCKED)}, "refuses the merge"),
        ({"state": replace(READY, readiness=Readiness.UNKNOWN)}, "not yet said"),
    ],
)
def test_every_missing_condition_is_a_no_that_says_why(
    changes: dict[str, object], says: str
) -> None:
    allowed, reason = verdict(**changes)
    assert allowed is False
    assert says in reason


def test_a_deletion_is_never_merged_even_if_a_policy_named_it() -> None:
    """The database refuses such a policy; the rule refuses it again."""
    deletion = WasteClass.SNAPSHOT_AGED
    allowed, reason = verdict(waste_class=deletion, allowed_classes=frozenset({deletion}))
    assert allowed is False
    assert "not reversible" in reason
