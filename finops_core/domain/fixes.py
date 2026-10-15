"""Which fixes Meter may merge, and when. FEAT-094, TASK-P15-001, ADR-0038.

**Reversible is in the domain, not in configuration.** A class of fix is reversible when undoing
it loses nothing: a volume moved from gp2 to gp3 is moved back by a second change, where a deleted
volume or snapshot is gone. Only a reversible class may ever be merged by Meter, and adding one is
a change to ADR-0038, not a setting, so no configuration can make a deletion mergeable.

**The rule is pure.** It decides from the tenant's merge policy, the fix's class, whether Meter
opened the pull request, and what the code host reports, and says why when the answer is no. The
one function that merges calls it first, `finops_ingest.fix_merge`, and nothing else merges.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from finops_core.domain.waste import WasteClass

#: The classes whose fix loses nothing if it is wrong. ADR-0038; gp2 to gp3 alone in P15.
REVERSIBLE: Final[frozenset[WasteClass]] = frozenset({WasteClass.EBS_GP2_TO_GP3})


class Readiness(StrEnum):
    """Whether the repository would accept a merge now, as its code host reports it."""

    #: Mergeable, every required check passed and every required review given.
    READY = "READY"
    #: A required check is still running, or a required review is not yet given.
    WAITING = "WAITING"
    #: A conflict, a failing check, or a branch behind a base it must be up to date with.
    BLOCKED = "BLOCKED"
    #: The host has not yet worked it out.
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, kw_only=True)
class PullRequestState:
    """One pull request as its code host reports it."""

    number: int
    url: str
    open: bool
    merged: bool
    readiness: Readiness
    #: The commit a merge would merge, so a push after the check cannot slip into the merge.
    head_sha: str
    #: The host's login of whoever merged it, where it was merged.
    merged_by: str | None = None


@dataclass(frozen=True)
class MergeVerdict:
    """Whether Meter may merge, and the sentence saying why or why not."""

    allowed: bool
    reason: str


WAITING_ON: Final[dict[Readiness, str]] = {
    Readiness.WAITING: "The repository's required checks or reviews have not all passed yet.",
    Readiness.BLOCKED: (
        "The repository refuses the merge as it stands: a conflict, a failing check, or a branch "
        "behind its base."
    ),
    Readiness.UNKNOWN: "The code host has not yet said whether it can be merged.",
}


def may_merge(
    *,
    waste_class: WasteClass,
    allowed_classes: frozenset[WasteClass],
    opened_by_meter: bool,
    state: PullRequestState,
    merging_on: bool,
) -> MergeVerdict:
    """Whether Meter may merge this pull request now. Every no says why. ADR-0038."""
    name = waste_class.value
    if not merging_on:
        return MergeVerdict(False, "Merging is turned off for every fix, `pull_request_merge`.")
    if waste_class not in REVERSIBLE:
        return MergeVerdict(
            False, f"A {name} fix is not reversible, so Meter never merges it; a person does."
        )
    if waste_class not in allowed_classes:
        return MergeVerdict(False, f"The merge policy does not name {name}; a person merges it.")
    if not opened_by_meter:
        return MergeVerdict(False, "Meter merges only a pull request it opened.")
    if state.merged:
        return MergeVerdict(False, "It is already merged.")
    if not state.open:
        return MergeVerdict(False, "It was closed without merging.")
    if state.readiness is not Readiness.READY:
        return MergeVerdict(False, WAITING_ON[state.readiness])
    return MergeVerdict(
        True,
        f"The merge policy names {name}, and the repository's required checks and reviews have "
        "passed.",
    )
