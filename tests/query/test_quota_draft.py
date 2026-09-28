"""The increase Meter would ask for, and the four times it refuses to ask.

FEAT-034, P5 spec section 6. The rule is arithmetic and two strings, so the cases worth having
are the refusals and the working.

**The refusals are the substance.** A draft offered against a hard limit wastes somebody's
afternoon and teaches them the drafts here are not to be trusted, and a draft sized from a
usage nobody measured is a guess dressed as arithmetic. Each refusal is a sentence for the
same reason an unmeasurable quota's reason is.

**The working has to name what a reader would argue with.** The target headroom is a decision
rather than a measurement, so it appears in the sentence: a reader who thinks forty percent is
too generous can see which number to dispute rather than concluding the whole suggestion is
arbitrary.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from finops_query.quota import (
    ALREADY_ROOMY,
    NO_LIMIT,
    NOT_ADJUSTABLE,
    NOT_MEASURED,
    ROUNDING_STEP,
    TARGET_HEADROOM,
    DraftRefused,
    IncreaseDraft,
    cli_command,
    console_url,
    draft_for,
    suggested_value,
)

SERVICE = "ec2"
QUOTA = "L-1216C47A"
REGION = "eu-west-1"


def draft(**overrides: object) -> IncreaseDraft | DraftRefused:
    values: dict[str, object] = {
        "service_code": SERVICE,
        "quota_code": QUOTA,
        "region_id": REGION,
        "current_limit": Decimal("320"),
        "observed_usage": Decimal("307"),
        "is_adjustable": True,
    }
    values.update(overrides)
    return draft_for(**values)  # type: ignore[arg-type]


def offered(**overrides: object) -> IncreaseDraft:
    outcome = draft(**overrides)
    assert isinstance(outcome, IncreaseDraft), f"expected a draft, got {outcome}"
    return outcome


def refused(**overrides: object) -> DraftRefused:
    outcome = draft(**overrides)
    assert isinstance(outcome, DraftRefused), f"expected a refusal, got {outcome}"
    return outcome


# --- the number ---------------------------------------------------------------


def test_the_suggestion_leaves_the_target_headroom_above_the_peak() -> None:
    """307 needing 40 percent free means 512, rounded up to 520."""
    assert suggested_value(Decimal("307")) == Decimal("520")


def test_the_suggestion_is_always_rounded_up_and_never_down() -> None:
    """A raised limit that still leaves the estate tight costs a support case and buys nothing.

    Checked across a range rather than on one value, because a rounding that went the other way
    would be right for exactly the inputs that land on a step.
    """
    for peak in range(1, 400, 7):
        observed = Decimal(peak)
        suggested = suggested_value(observed)
        needed = observed / (Decimal(1) - TARGET_HEADROOM)
        assert suggested >= needed
        assert suggested - needed < ROUNDING_STEP
        assert suggested % ROUNDING_STEP == 0


def test_the_working_names_the_peak_the_limit_and_the_target() -> None:
    """All three, because a reader who disagrees needs to know which one to dispute."""
    working = offered().working
    assert "307" in working
    assert "320" in working
    assert "40" in working
    assert "520" in working


def test_the_working_says_meter_does_not_submit_it() -> None:
    """The claim travels with the number rather than only on a screen that could drop it."""
    assert "does not submit" in offered().working


# --- the four refusals --------------------------------------------------------


def test_a_hard_limit_gets_no_draft() -> None:
    """AWS does not raise it, so the way past it is a different architecture."""
    assert refused(is_adjustable=False).reason == NOT_ADJUSTABLE


def test_a_quota_with_no_usage_gets_no_draft() -> None:
    """There is no observed peak to size a request from, so any number would be invented.

    This is the refusal that matters most, because it is the one a helpful implementation would
    skip: suggesting double the current limit needs no measurement and looks useful.
    """
    assert refused(observed_usage=None).reason == NOT_MEASURED


def test_a_quota_with_no_published_limit_gets_no_draft() -> None:
    assert refused(current_limit=None).reason == NO_LIMIT


def test_a_quota_with_room_to_spare_gets_no_draft() -> None:
    """Asking for more of something an account is not short of wastes a reviewer's time."""
    assert refused(observed_usage=Decimal("10")).reason == ALREADY_ROOMY


def test_every_refusal_is_a_sentence_rather_than_a_token() -> None:
    """A refusal reading "not eligible" teaches a reader the explanations here are empty."""
    for reason in (NOT_ADJUSTABLE, NOT_MEASURED, NO_LIMIT, ALREADY_ROOMY):
        assert len(reason.split()) > 8, reason
        assert reason.endswith(".")


def test_the_refusals_are_all_different() -> None:
    """Four causes and four sentences. One reused sentence would collapse four fixes into one."""
    assert len({NOT_ADJUSTABLE, NOT_MEASURED, NO_LIMIT, ALREADY_ROOMY}) == 4


def test_the_hard_limit_refusal_wins_over_the_others() -> None:
    """Ordered by what a reader can do about it, and nothing changes a hard limit."""
    outcome = refused(is_adjustable=False, observed_usage=None, current_limit=None)
    assert outcome.reason == NOT_ADJUSTABLE


# --- the two things a person pastes -------------------------------------------


def test_the_command_is_the_cli_spelling_and_not_the_api_name() -> None:
    """A command a person runs is a different act from a call Meter makes.

    The two are spelled differently so `tests/contract/test_no_quota_writes.py` can hold the
    second one absent without forbidding the first.
    """
    command = offered().cli_command
    assert "request-service-quota-increase" in command
    assert "RequestServiceQuota" not in command


def test_the_command_carries_every_argument_the_call_needs() -> None:
    """Exact and copyable, so the human step is a paste rather than research."""
    command = offered().cli_command
    for fragment in (
        "--service-code ec2",
        f"--quota-code {QUOTA}",
        "--desired-value 520",
        f"--region {REGION}",
    ):
        assert fragment in command, command


def test_a_global_quota_omits_the_region_rather_than_guessing_one() -> None:
    """A hardcoded region is an assumption that breaks where being wrong costs the most.

    Omitted from both, so the command runs against whatever the caller has configured and the
    link opens wherever the console already is.
    """
    outcome = offered(region_id=None)
    assert "--region" not in outcome.cli_command
    assert outcome.console_url == (
        f"https://console.aws.amazon.com/servicequotas/home/services/{SERVICE}/quotas/{QUOTA}"
    )


def test_the_console_link_is_regional_where_the_quota_is() -> None:
    assert offered().console_url == (
        f"https://{REGION}.console.aws.amazon.com/servicequotas/home/services/"
        f"{SERVICE}/quotas/{QUOTA}"
    )


@pytest.mark.parametrize("region", [REGION, None])
def test_the_link_and_the_command_agree_about_the_value(region: str | None) -> None:
    """Two strings from one number, so a reader cannot paste a command for a different figure."""
    outcome = offered(region_id=region)
    assert f"{outcome.suggested_value.normalize():f}" in outcome.cli_command
    assert console_url(SERVICE, QUOTA, region) == outcome.console_url
    assert cli_command(SERVICE, QUOTA, region, outcome.suggested_value) == outcome.cli_command
