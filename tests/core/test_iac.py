"""The three valued answer, and the two things that have to hold before we say unmanaged.

FEAT-057, TASK-P4-013. Pure.

Every case here is about one claim: reading state tells you what is managed and never what is
not. `UNMANAGED` tells somebody to import a resource or write it into code, and doing that to a
resource already inside a module somebody else owns produces a duplicate, a state conflict, or
a second copy of a live resource. So the tests that matter are the ones asserting we refuse to
say it.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from finops_core.domain.iac import (
    ManagedResource,
    ManagementState,
    StateRead,
    management_of,
)

NOW = datetime(2026, 9, 26, 6, 0, tzinfo=UTC)
VPC = "arn:aws:ec2:eu-west-1:111122223333:vpc/vpc-main"
BUCKET = "arn:aws:s3:::example-data"
MINE = "111122223333"


def managed(
    provider_id: str = VPC, address: str = "module.network.aws_vpc.main"
) -> ManagedResource:
    return ManagedResource(
        provider_id=provider_id,
        address=address,
        state_reference="s3://example-state/network.tfstate",
        as_of=NOW,
        collected_at=NOW,
    )


def answer(
    provider_id: str,
    *,
    found: frozenset[str] = frozenset({VPC}),
    exhaustive: frozenset[str] = frozenset(),
    whole: bool = True,
) -> ManagementState:
    return management_of(
        provider_id,
        managed=found,
        account_id=MINE,
        exhaustive_accounts=exhaustive,
        read_was_whole=whole,
    )


def test_a_resource_in_the_state_is_managed() -> None:
    """The only one of the three that rests on evidence rather than on a declaration."""
    assert answer(VPC) is ManagementState.MANAGED


def test_a_resource_absent_from_the_state_is_not_determined_by_default() -> None:
    """The default, and the case this module exists for. Nothing in a state file says whether
    it is the only state file in the organization, so absence carries no information."""
    assert answer(BUCKET) is ManagementState.NOT_DETERMINED


def test_unmanaged_needs_a_declaration_about_our_own_configuration() -> None:
    """Absence becomes evidence only once an operator has said the backends we read are the
    whole of the infrastructure as code for that account. The declaration is about our
    configuration and not about the cloud, which is why it cannot be inferred."""
    assert answer(BUCKET, exhaustive=frozenset({MINE})) is ManagementState.UNMANAGED


def test_a_declaration_for_another_account_does_not_carry_across() -> None:
    """Per account, because an operator who onboards a second team's workspace has declared
    nothing about the first team's."""
    assert answer(BUCKET, exhaustive=frozenset({"444455556666"})) is ManagementState.NOT_DETERMINED


def test_a_declaration_is_worth_nothing_on_a_partial_read() -> None:
    """The second condition, and the one a naive implementation drops. A run where one backend
    refused us would otherwise report every resource in that backend as unmanaged, on the
    strength of a failure, and somebody would import a resource that was already in code."""
    assert (
        answer(BUCKET, exhaustive=frozenset({MINE}), whole=False) is ManagementState.NOT_DETERMINED
    )


def test_a_managed_resource_stays_managed_on_a_partial_read() -> None:
    """The asymmetry is the point. A partial read cannot prove absence and still proves
    presence, so a resource we found is managed whatever else failed."""
    assert answer(VPC, whole=False) is ManagementState.MANAGED


# --- what a read reports ----------------------------------------------------


def test_a_read_with_no_refusals_is_whole() -> None:
    assert StateRead(managed=(managed(),)).is_whole


def test_a_read_that_lost_one_location_is_not_whole() -> None:
    """And it still carries what it found. A read that discarded its results on one failure
    would make a single unreachable backend look like an estate with no code at all."""
    partial = StateRead(
        managed=(managed(),),
        refused=(("s3://other-state/app.tfstate", "AccessDenied"),),
    )
    assert not partial.is_whole
    assert len(partial.managed) == 1


def test_a_refusal_names_the_location_and_the_typed_cause() -> None:
    """Both, because a screen that says something went wrong sends nobody anywhere. The cause
    is from the taxonomy rather than free text, so a persistent gap can be grouped."""
    location, cause = StateRead(
        managed=(), refused=(("s3://x/y.tfstate", "AccessDenied"),)
    ).refused[0]
    assert location.startswith("s3://")
    assert cause == "AccessDenied"


def test_the_address_is_the_module_path_rather_than_the_resource_name_alone() -> None:
    """FEAT-040 opens a pull request against a block. A bare resource name appears in every
    module that declares one, so an address without its module path names no file."""
    assert managed().address == "module.network.aws_vpc.main"


@pytest.mark.parametrize("state", list(ManagementState))
def test_every_state_is_a_word_rather_than_a_boolean(state: ManagementState) -> None:
    """Three values, so the enumeration cannot be stored in a column that holds two. A boolean
    is what conflates "we did not find it" with "nobody manages it"."""
    assert isinstance(state.value, str)
