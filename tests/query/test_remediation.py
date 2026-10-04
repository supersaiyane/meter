"""Remediation as a pull request: authored whole, opened once, and nothing applied.

TASK-P7-009. The plan's criteria, plus the three refusals that keep a pull request honest:
nothing manages the resource, the remedy needs a value nobody recorded, or the address
names one instance of several.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from finops_core.domain.waste import WasteClass
from finops_core.ports import pull_requests
from finops_core.ports.pull_requests import PullRequestDraft, PullRequestSink
from finops_fakes.pull_requests import RecordingPullRequests
from finops_query import remediation
from finops_query.remediation import (
    Management,
    NotAuthored,
    Proposed,
    RecommendationFacts,
    author,
    propose,
)

ADDRESS = "module.storage.aws_ebs_volume.scratch"
MANAGED = Management(address=ADDRESS, state_reference="s3://estate-state/storage.tfstate")


def recommendation(**overrides: Any) -> RecommendationFacts:
    fields: dict[str, Any] = {
        "recommendation_id": "rec-41",
        "waste_class": WasteClass.EBS_UNATTACHED,
        "resource_id": "vol-0f1e2d3c4b5a69788",
        "sub_account_id": "fake-platform-a",
        "region_id": "eu-west-1",
        "estimated_monthly_saving": Decimal("38.40"),
        "confidence": "HIGH",
        "rationale": "Unattached for every day of the observation window.",
        "as_of": datetime(2026, 9, 30, tzinfo=UTC),
    }
    fields.update(overrides)
    return RecommendationFacts(**fields)


def drafted(*args: Any) -> PullRequestDraft:
    draft = author(*args)
    assert isinstance(draft, PullRequestDraft), draft
    return draft


# --- what is authored ------------------------------------------------------------------


def test_a_removal_is_authored_as_a_removed_block_naming_the_address() -> None:
    draft = drafted(recommendation(), MANAGED, "narrow")

    (change,) = draft.changes
    assert change.path == "meter/remediation/rec-41.tf"
    assert f"from = {ADDRESS}" in change.content
    assert "destroy = true" in change.content
    assert (draft.branch, draft.reference) == ("meter/remediation/rec-41", "rec-41")


def test_the_body_carries_the_recommendation_its_saving_provenance_and_blast_radius() -> None:
    body = drafted(recommendation(), MANAGED, "narrow").body

    for said in ("rec-41", "EBS_UNATTACHED", "38.40 USD, modelled", "Blast radius: narrow"):
        assert said in body, said
    assert "delete the resource block" in body, "the reviewer is told the change is unfinished"


def test_a_blast_radius_nobody_computed_is_said_rather_than_left_blank() -> None:
    body = drafted(recommendation(), MANAGED, None).body
    assert "Blast radius: not computed" in body


# --- what is refused, and why -----------------------------------------------------------


def test_a_resource_nothing_manages_is_refused_naming_that() -> None:
    refused = author(recommendation(), None, "narrow")
    assert isinstance(refused, NotAuthored)
    assert "No infrastructure as code address manages vol-0f1e2d3c4b5a69788" in refused.reason


@pytest.mark.parametrize(
    "waste_class",
    [WasteClass.RIGHTSIZE_INSTANCE, WasteClass.EBS_GP2_TO_GP3, WasteClass.COMMITMENT_UNCOVERED],
)
def test_a_remedy_needing_a_value_nobody_recorded_is_refused(waste_class: WasteClass) -> None:
    refused = author(recommendation(waste_class=waste_class), MANAGED, "narrow")
    assert isinstance(refused, NotAuthored)
    assert "guessed value is not authored" in refused.reason


@pytest.mark.parametrize(
    "address", ["aws_instance.web[0]", 'module.app["blue"].aws_ebs_volume.scratch']
)
def test_an_address_naming_one_instance_of_several_is_refused(address: str) -> None:
    refused = author(recommendation(), Management(address=address, state_reference="s"), None)
    assert isinstance(refused, NotAuthored)
    assert "every instance" in refused.reason


# --- opened, once, and nothing more -------------------------------------------------------


def test_an_authored_change_is_opened_for_review_exactly_once() -> None:
    host = RecordingPullRequests()

    first = propose(recommendation(), MANAGED, "narrow", host)
    second = propose(recommendation(), MANAGED, "narrow", host)

    assert isinstance(first, Proposed) and isinstance(second, Proposed)
    assert first.host_reference == second.host_reference
    assert len(host.drafts) == 1
    assert isinstance(host, PullRequestSink)


def test_a_refused_change_reaches_no_host() -> None:
    host = RecordingPullRequests()
    assert isinstance(propose(recommendation(), None, None, host), NotAuthored)
    assert host.drafts == ()


def test_the_port_can_open_and_nothing_else() -> None:
    """No merge, approve or apply to implement, so no adapter can have one."""
    methods = {
        name
        for name, member in vars(PullRequestSink).items()
        if callable(member) and not name.startswith("_")
    }
    assert methods == {"open_pull_request"}


@pytest.mark.parametrize("module", [remediation, pull_requests])
def test_no_code_here_names_a_merge_an_approve_or_an_apply(module: object) -> None:
    """Names in code, not words in prose: the body promises never to merge, in a sentence."""
    tree = ast.parse(Path(str(getattr(module, "__file__", ""))).read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    names |= {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.ClassDef)
    }
    forbidden = [
        name for name in names if any(w in name.lower() for w in ("merge", "approve", "apply"))
    ]
    assert forbidden == []
