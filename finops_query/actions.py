"""What applying a finding costs if it turns out to be wrong.

FEAT-052. Adopted from the 2026-09-26 IBM Turbonomic review, whose Top Actions surface ranks
the five most valuable actions per category and flags the ones a reader can apply
immediately with minimal risk.

**We cannot copy the flag, because we cannot apply anything.** Meter is read only in v1,
constraint 6, so "executable immediately" has no meaning here. What transfers is the
judgement underneath it: some changes can be undone and some cannot, and a reader deciding
what to do before lunch needs to know which.

**Risk is two independent questions, and neither of them is confidence.** A high confidence
rightsizing still needs a restart. A low confidence snapshot deletion is still permanent.
`confidence` comes from the length of the observation window and says nothing about either
of these, so collapsing them into one number would be wrong in both directions.

1. **Is it reversible?** Can the change be put back with nothing lost?
2. **Does it disturb running work?** Does applying it interrupt, restart or throttle
   something that is serving traffic?

A finding with no regret is reversible and disturbs nothing. Three of the seventeen waste
classes qualify.

**The useful part is which ones do not.** The three findings that read as safest to somebody
scanning a list are releasing an unassociated Elastic IP, deleting an unattached volume, and
setting a retention period on a log group that has none. All three are permanent. Releasing
an address means the same address is never reissued and anything allow listing it fails
afterwards. Setting a retention period deletes everything already older than it,
immediately. A surface that called those low risk because nothing was running would teach
exactly the wrong lesson, which is why the table below is explicit per class and why every
entry carries a sentence rather than only the two flags.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from finops_core.domain.waste import WasteClass


@dataclass(frozen=True)
class Risk:
    """What one class of change costs if it is wrong, and the sentence saying why.

    `why` is not decoration. The two flags are what a screen sorts and filters on; the
    sentence is what a reader needs before touching production, and a flag with no sentence
    behind it is a label somebody will disagree with and be unable to argue against.
    """

    #: True where the change can be put back with nothing lost. A resize is reversible. A
    #: deletion is not, whatever the thing deleted was doing.
    reversible: bool
    #: True where applying it interrupts, restarts or throttles something serving traffic.
    #: Deliberately not the same question as whether the resource is idle: an idle instance
    #: still has to be stopped to be resized.
    disturbs_running_work: bool
    why: str

    @property
    def is_no_regret(self) -> bool:
        """Reversible and disturbing nothing. Both halves, and nothing else.

        Not a synonym for safe, and the module docstring says why: a change with no regret
        is one a reader can try and undo, which is a much narrower claim than one that will
        turn out well.
        """
        return self.reversible and not self.disturbs_running_work


#: Every waste class, with what applying it would cost. Total over `WasteClass`, which
#: `tests/query/test_actions.py` asserts: a class added to the domain without a row here
#: fails the build rather than reaching a screen with no risk statement, because every
#: default available at that point is a lie in one direction or the other.
RISK_OF: Mapping[WasteClass, Risk] = {
    WasteClass.RIGHTSIZE_INSTANCE: Risk(
        reversible=True,
        disturbs_running_work=True,
        why=(
            "A resize needs a stop and a start, so the workload is interrupted. The instance "
            "type can be set back afterwards."
        ),
    ),
    WasteClass.IDLE_INSTANCE: Risk(
        reversible=False,
        disturbs_running_work=True,
        why=(
            "Termination is final. Anything on the instance store is gone and the instance "
            "identifier is not reissued, so this is not undone by launching another one."
        ),
    ),
    WasteClass.GRAVITON_CANDIDATE: Risk(
        reversible=True,
        disturbs_running_work=True,
        why=(
            "A different processor architecture, so every binary on the instance has to run "
            "on arm64. Reversible, and the most likely finding on this list to fail in a way "
            "the bill cannot see."
        ),
    ),
    WasteClass.EBS_OVERPROVISIONED: Risk(
        reversible=False,
        disturbs_running_work=True,
        why=(
            "An EBS volume cannot be shrunk in place. The route is a snapshot, a smaller new "
            "volume and a detach, and the old data goes when the old volume does."
        ),
    ),
    WasteClass.EBS_GP2_TO_GP3: Risk(
        reversible=True,
        disturbs_running_work=False,
        why=(
            "A volume type change is applied online and can be changed back. Nothing detaches "
            "and nothing restarts."
        ),
    ),
    WasteClass.EBS_UNATTACHED: Risk(
        reversible=False,
        disturbs_running_work=False,
        why=(
            "Deleting a volume is final. It is attached to nothing, so nothing stops, and "
            "nothing gets the data back either. It reads as safe because of the first half."
        ),
    ),
    WasteClass.SNAPSHOT_AGED: Risk(
        reversible=False,
        disturbs_running_work=False,
        why=(
            "A deleted snapshot is gone. It is either the restore path for something or it is "
            "not, and its age is the only evidence this finding has either way."
        ),
    ),
    WasteClass.NAT_GATEWAY_IDLE: Risk(
        reversible=False,
        disturbs_running_work=True,
        why=(
            "A replacement gateway gets a new address and the route tables have to be edited "
            "to reach it, so deleting one is not a change that is simply put back."
        ),
    ),
    WasteClass.LOAD_BALANCER_IDLE: Risk(
        reversible=False,
        disturbs_running_work=True,
        why=(
            "A replacement load balancer gets a new DNS name, so anything holding the old one "
            "has to be changed as well. The name is the part that cannot be recreated."
        ),
    ),
    WasteClass.ELASTIC_IP_UNASSOCIATED: Risk(
        reversible=False,
        disturbs_running_work=False,
        why=(
            "Releasing an address is final: the same address is not reissued, and anything "
            "that allow lists it fails afterwards without saying why. This is the finding on "
            "this list that looks safest and is not."
        ),
    ),
    WasteClass.DYNAMODB_OVERPROVISIONED: Risk(
        reversible=True,
        disturbs_running_work=True,
        why=(
            "Provisioned capacity changes online and changes back, and a reduction that goes "
            "too far throttles live requests. That is a workload effect rather than a billing "
            "one, which is why it counts as disturbing running work."
        ),
    ),
    WasteClass.LOG_GROUP_NO_RETENTION: Risk(
        reversible=False,
        disturbs_running_work=False,
        why=(
            "Setting a retention period deletes everything already older than it, immediately "
            "and permanently. The second finding here that reads as safe and destroys data."
        ),
    ),
    WasteClass.LOG_GROUP_UNQUERIED: Risk(
        reversible=False,
        disturbs_running_work=False,
        why=(
            "The action is a shorter retention or a stopped delivery. The first deletes what "
            "is already past the new period. The second is reversible, and the gap it leaves "
            "in the logs is not."
        ),
    ),
    WasteClass.LOG_DUPLICATE_DELIVERY: Risk(
        reversible=True,
        disturbs_running_work=False,
        why=(
            "Removing one of two deliveries of the same log leaves the other, and the "
            "subscription can be recreated from its own definition. The duplicate has to "
            "actually be a duplicate, which is what the finding's evidence is for."
        ),
    ),
    WasteClass.METRIC_UNQUERIED: Risk(
        reversible=True,
        disturbs_running_work=True,
        why=(
            "Stopping a custom metric is a change in application code, so it ships like any "
            "other change and reverts like one. It counts as disturbing work because it is a "
            "deployment rather than a console setting."
        ),
    ),
    WasteClass.ALARM_INSUFFICIENT_DATA: Risk(
        reversible=True,
        disturbs_running_work=False,
        why=(
            "An alarm can be recreated from its own definition, and one that has never left "
            "insufficient data has never fired. Deleting it removes no coverage that existed."
        ),
    ),
    WasteClass.CONTAINER_RIGHTSIZE: Risk(
        reversible=True,
        disturbs_running_work=True,
        why=(
            "A request or limit change restarts the pod, and the values can be set back. A "
            "limit set too low is an out of memory kill rather than a slow workload, which is "
            "why this is never a no regret change."
        ),
    ),
}


def risk_of(waste_class: WasteClass) -> Risk:
    """The risk of one class.

    Raises:
        KeyError: The class has no row. Deliberately not a default, because every default
            available here is a lie: reversible would understate a deletion and
            irreversible would overstate a resize, and a screen would show one of them.
    """
    return RISK_OF[waste_class]


#: The classes a reader can try and undo. Derived rather than listed, so it cannot drift
#: from the table above, and small enough that the number itself is worth knowing: three of
#: seventeen. A surface promising a page of safe wins would be inventing most of them.
NO_REGRET_CLASSES: frozenset[WasteClass] = frozenset(
    waste_class for waste_class, risk in RISK_OF.items() if risk.is_no_regret
)
