"""The one place Meter merges. ADR-0038, FEAT-094, TASK-P15-001.

The host is asked to merge only when the rule says yes, at the head the host reported; a merge
the host refuses is an answer recorded as such, and nothing is asked of the host otherwise.
"""

from __future__ import annotations

from finops_core.domain.fixes import PullRequestState, Readiness
from finops_core.domain.waste import WasteClass
from finops_fakes.pull_requests import RecordingMerger
from finops_ingest.fix_merge import MergeOutcome, merge_under_policy

GP3 = WasteClass.EBS_GP2_TO_GP3
REPOSITORY = "acme/infra"


def state(readiness: Readiness = Readiness.READY) -> PullRequestState:
    return PullRequestState(
        number=7,
        url="https://code.example/acme/infra/pull/7",
        open=True,
        merged=False,
        readiness=readiness,
        head_sha="head-7",
    )


def merge(merger: RecordingMerger, **changes: object) -> MergeOutcome:
    arguments: dict[str, object] = {
        "repository": REPOSITORY,
        "state": state(),
        "waste_class": GP3,
        "allowed_classes": frozenset({GP3}),
        "opened_by_meter": True,
        "merging_on": True,
    }
    arguments.update(changes)
    return merge_under_policy(merger, **arguments)  # type: ignore[arg-type]


def test_a_fix_the_rule_allows_is_merged_at_the_head_the_host_reported() -> None:
    merger = RecordingMerger()
    outcome = merge(merger)
    assert (outcome.merged, outcome.attempted, outcome.sha) == (True, True, "merge-7")
    assert merger.merges == [(REPOSITORY, 7, "head-7")]


def test_nothing_is_asked_of_the_host_when_the_rule_says_no() -> None:
    merger = RecordingMerger()
    refusals: tuple[dict[str, object], ...] = (
        {"merging_on": False},
        {"waste_class": WasteClass.EBS_UNATTACHED, "allowed_classes": frozenset({GP3})},
        {"allowed_classes": frozenset()},
        {"state": state(Readiness.WAITING)},
    )
    for changes in refusals:
        outcome = merge(merger, **changes)
        assert (outcome.merged, outcome.attempted) == (False, False), changes
    assert merger.merges == []


def test_a_merge_the_host_refuses_is_recorded_as_refused() -> None:
    merger = RecordingMerger(accept=False)
    outcome = merge(merger)
    assert (outcome.merged, outcome.attempted) == (False, True)
    assert outcome.reason == "The fake host refused the merge."
