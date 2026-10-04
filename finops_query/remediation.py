"""A recommendation, authored as an infrastructure change for a person to approve.

TASK-P7-009 and FEAT-040, P7 spec section 3 and constraint 6. The objection FEAT-034
answered for a quota increase applies here with the same answer: delivering a change as a
pull request costs the person one review, and buys the sentence that this product has
never changed anything in a customer account.

**Authored and opened, and nothing more.** The change is written in full here, then handed
to a `PullRequestSink`, whose one method opens a pull request. Nothing in this module or
the port can apply, merge or approve one, and `tests/contract/test_no_llm_writes.py` holds
that by name across the production packages.

**Only what can be written without guessing.** FEAT-057 knows the Terraform address that
manages a resource and the state that holds it. It does not hold the source file the
address is declared in, so the one change this can author whole is a removal: a `removed`
block naming the address, which the reviewer pairs with deleting the resource's block in
the same change, and the body says exactly that. A recommendation needing a new value, a
smaller size or another volume type, is refused naming the value it lacks, because a pull
request carrying an invented size is a guess with a reviewer's signature on it.

**A resource nothing manages is refused, naming that.** FEAT-057 records when no address
manages a resource, and that absence is a real state rather than a gap to fill: such a
resource was made by hand, and a change to it belongs to whoever made it.

Terraform only. No collector reads CloudFormation, so there is no address to author one
against, and the refusal says so rather than writing a template for a stack nobody named.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from finops_core.domain.waste import WasteClass
from finops_core.ports.pull_requests import FileChange, PullRequestDraft, PullRequestSink

#: The classes whose remedy is to remove the resource. Each needs nothing the product
#: does not already hold, so each can be authored whole.
REMOVALS = frozenset(
    {
        WasteClass.IDLE_INSTANCE,
        WasteClass.EBS_UNATTACHED,
        WasteClass.SNAPSHOT_AGED,
        WasteClass.NAT_GATEWAY_IDLE,
        WasteClass.LOAD_BALANCER_IDLE,
        WasteClass.ELASTIC_IP_UNASSOCIATED,
        WasteClass.ALARM_INSUFFICIENT_DATA,
        WasteClass.LOG_GROUP_UNQUERIED,
    }
)

#: A Terraform address naming one instance of a resource, `aws_instance.web[0]` or
#: `module.app["blue"].aws_instance.web`. A `removed` block cannot name an instance, so it
#: would remove every instance, which is not what was recommended.
INSTANCE_KEY = re.compile(r"\[[^\]]*\]")

#: Where the authored file goes, relative to the repository the host adapter is pointed at.
REMEDIATION_DIRECTORY = "meter/remediation"


@dataclass(frozen=True)
class RecommendationFacts:
    """The recommendation as it was stored, and what its saving is."""

    recommendation_id: str
    waste_class: WasteClass
    resource_id: str
    sub_account_id: str
    region_id: str
    #: An estimate, so modelled, and the body says so beside the figure.
    estimated_monthly_saving: Decimal
    confidence: str
    rationale: str
    as_of: datetime


@dataclass(frozen=True)
class Management:
    """What FEAT-057 knows about the infrastructure as code behind a resource."""

    address: str
    state_reference: str


@dataclass(frozen=True)
class NotAuthored:
    """No pull request, and the sentence saying why."""

    reason: str


@dataclass(frozen=True)
class Proposed:
    """A pull request the host opened for review, and what it holds."""

    draft: PullRequestDraft
    host_reference: str


def author(
    recommendation: RecommendationFacts,
    management: Management | None,
    blast_radius_band: str | None,
) -> PullRequestDraft | NotAuthored:
    """The pull request for `recommendation`, or why there is none."""
    if management is None:
        return NotAuthored(
            reason=(
                f"No infrastructure as code address manages {recommendation.resource_id}, "
                f"FEAT-057, so there is no file to change. It was made outside Terraform, and "
                f"a change to it belongs to whoever made it."
            )
        )
    if recommendation.waste_class not in REMOVALS:
        return NotAuthored(
            reason=(
                f"A {recommendation.waste_class.value} recommendation needs a new value, and "
                f"this product does not record the value it would set or the source file it "
                f"would set it in. A pull request carrying a guessed value is not authored."
            )
        )
    if INSTANCE_KEY.search(management.address):
        return NotAuthored(
            reason=(
                f"{management.address} names one instance of a resource, and a removed block "
                f"can only remove every instance, which is not what was recommended."
            )
        )
    return PullRequestDraft(
        title=f"Remove {management.address}, an idle resource Meter found",
        body=_body(recommendation, management, blast_radius_band),
        branch=f"meter/remediation/{recommendation.recommendation_id}",
        changes=(
            FileChange(
                path=f"{REMEDIATION_DIRECTORY}/{recommendation.recommendation_id}.tf",
                content=_removed_block(recommendation, management),
            ),
        ),
        reference=recommendation.recommendation_id,
    )


def propose(
    recommendation: RecommendationFacts,
    management: Management | None,
    blast_radius_band: str | None,
    sink: PullRequestSink,
) -> Proposed | NotAuthored:
    """Author the change, and open it for review if one could be authored.

    Raises:
        AccessDenied, Misconfigured, Unreachable: As the sink raises them.
    """
    draft = author(recommendation, management, blast_radius_band)
    if isinstance(draft, NotAuthored):
        return draft
    return Proposed(draft=draft, host_reference=sink.open_pull_request(draft))


def _removed_block(recommendation: RecommendationFacts, management: Management) -> str:
    return (
        f"# Authored by Meter for recommendation {recommendation.recommendation_id}.\n"
        f"# Delete the resource block for {management.address} in this same change:\n"
        f"# Terraform will not plan while the block and this removal both exist.\n"
        f"removed {{\n"
        f"  from = {management.address}\n"
        f"\n"
        f"  lifecycle {{\n"
        f"    destroy = true\n"
        f"  }}\n"
        f"}}\n"
    )


def _body(recommendation: RecommendationFacts, management: Management, band: str | None) -> str:
    blast = band if band else "not computed, so read the dependency graph before approving"
    return "\n".join(
        (
            f"Meter recommends removing `{recommendation.resource_id}` in account "
            f"`{recommendation.sub_account_id}`, region `{recommendation.region_id}`.",
            "",
            f"- Recommendation: `{recommendation.recommendation_id}`, "
            f"{recommendation.waste_class.value}",
            f"- Why: {recommendation.rationale}",
            f"- Estimated monthly saving: {recommendation.estimated_monthly_saving} USD, "
            f"modelled, as of {recommendation.as_of.isoformat()}",
            f"- Confidence: {recommendation.confidence}",
            f"- Blast radius: {blast}",
            f"- Managed at: `{management.address}`, in state `{management.state_reference}`",
            "",
            f"To finish this change, delete the resource block for `{management.address}` "
            f"from its module in this branch. Terraform refuses to plan while both exist, so "
            f"this pull request cannot be applied as it stands.",
            "",
            "Meter opened this pull request and will never merge, approve or apply it.",
        )
    )
