"""The one place Meter merges a pull request. ADR-0038, FEAT-094, TASK-P15-001.

Every merge goes through `merge_under_policy`, which asks `finops_core.domain.fixes.may_merge`
first and merges only on a yes, at the head the host reported, through the host's own merge. The
contract test allows the merge method's name in this module, in the port that declares it and in
the adapter that implements it, and refuses it anywhere else, so a second path to a merge is a
failed build rather than a review comment.
"""

from __future__ import annotations

from dataclasses import dataclass

from finops_core.domain.fixes import PullRequestState, may_merge
from finops_core.domain.waste import WasteClass
from finops_core.ports.merges import PullRequestMerger


@dataclass(frozen=True)
class MergeOutcome:
    """Whether Meter merged, and the sentence saying why or why not."""

    merged: bool
    reason: str
    sha: str | None = None
    #: True when the rule said yes and the host was asked, whatever it answered.
    attempted: bool = False


def merge_under_policy(
    merger: PullRequestMerger,
    *,
    repository: str,
    state: PullRequestState,
    waste_class: WasteClass,
    allowed_classes: frozenset[WasteClass],
    opened_by_meter: bool,
    merging_on: bool,
) -> MergeOutcome:
    """Merge the pull request if the rule allows it now, and say what happened.

    Raises:
        AccessDenied, Throttled, Unreachable: As the merger raises them.
    """
    verdict = may_merge(
        waste_class=waste_class,
        allowed_classes=allowed_classes,
        opened_by_meter=opened_by_meter,
        state=state,
        merging_on=merging_on,
    )
    if not verdict.allowed:
        return MergeOutcome(merged=False, reason=verdict.reason)
    answer = merger.merge_pull_request(repository, state.number, state.head_sha)
    if not answer.merged:
        return MergeOutcome(merged=False, reason=answer.reason, attempted=True)
    return MergeOutcome(merged=True, reason=verdict.reason, sha=answer.sha, attempted=True)
