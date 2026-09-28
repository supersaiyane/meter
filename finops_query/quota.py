"""The increase Meter would ask for, and the two things a person pastes to ask for it.

FEAT-034, and P5 spec section 6. No provider import, so this is arithmetic and two strings.

**Nothing here submits anything, and the absence is enforced by name.** The API that would
do it is `RequestServiceQuotaIncrease`, and `tests/contract/test_no_quota_writes.py` fails if
that name appears in production code at all. What this module emits is the AWS CLI form,
`request-service-quota-increase`, which is a different string and is deliberately so: a
command for a person to run under their own credentials is not a call this product makes
under an assumed role, and the test can tell the two apart because they are spelled
differently.

**The suggested value has its working, and the working is the feature.** A number with no
derivation is one a reader either accepts or ignores, and both are bad: accepting it means
raising a limit on somebody's say so, and ignoring it means the draft was pointless. So the
sentence states the observed peak, the target headroom and the rounding, and anybody who
disagrees with the target can see which part to argue with.

**A draft is refused for a quota that cannot be raised or cannot be measured.** A hard limit
does not move, so a draft against one wastes an afternoon and teaches a reader the drafts
here are not to be trusted. And a quota with no usage figure has no basis for a number: any
suggestion would be a guess dressed as arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

#: The headroom a raised limit should leave above the observed peak.
#:
#: Forty percent, and the figure is a decision rather than a measurement, which is why it is
#: named here with its argument. Too small and the next quarter end asks for another increase,
#: which is the failure the draft exists to prevent: a support case takes days and a quota is
#: hit in minutes. Too large and the request looks unreasonable to whoever approves it, and an
#: unreasonable request is a denied one. A reader who disagrees can see the number and the
#: working, which is why both are published.
TARGET_HEADROOM = Decimal("0.4")

#: What the suggested value is rounded up to. A limit of 533 is a figure nobody chose, and a
#: reviewer reading a request for one wonders where it came from. A round number is easier to
#: approve and is never smaller than the honest figure, because the rounding is always upward.
ROUNDING_STEP = Decimal("10")

#: Why a draft was refused. Each is a sentence, for the same reason the unmeasurable reasons
#: on a quota are: a refusal reading "not eligible" teaches a reader the explanations here are
#: empty and they stop reading the ones that are not.
NOT_ADJUSTABLE = (
    "This is a hard limit and AWS does not raise it, so there is nothing to request. The way "
    "past it is a different architecture rather than a bigger number."
)
NOT_MEASURED = (
    "Nothing measures usage for this quota, so there is no observed peak to size a request "
    "from. A suggested value here would be arithmetic over a number nobody has."
)
NO_LIMIT = (
    "The provider publishes no limit for this quota, so there is nothing to raise and no "
    "figure to raise it from."
)
ALREADY_ROOMY = (
    "The observed peak already leaves more headroom than a request would ask for, so an "
    "increase would be asking for something this account is not short of."
)


@dataclass(frozen=True)
class IncreaseDraft:
    """A request a person can make, with the working behind its number.

    Meter never submits this. The two strings are for a human to paste, and the schema carries
    a column that can only say Meter did not.
    """

    service_code: str
    quota_code: str
    #: None where the quota is global. The console link and the command both change shape.
    region_id: str | None
    current_limit: Decimal
    observed_usage: Decimal
    suggested_value: Decimal
    #: How the suggestion was reached, in a sentence a reader can disagree with.
    working: str
    console_url: str
    cli_command: str


@dataclass(frozen=True)
class DraftRefused:
    """Why no draft was offered. Never rendered as an empty draft."""

    reason: str


def suggested_value(observed_usage: Decimal) -> Decimal:
    """The limit that would leave `TARGET_HEADROOM` above the observed peak.

    Rounded up, always, so the returned figure is never less than the honest one. A raised
    limit that still leaves the estate tight is the worst of the three outcomes: it costs a
    support case and buys nothing.
    """
    needed = observed_usage / (Decimal(1) - TARGET_HEADROOM)
    steps = (needed / ROUNDING_STEP).to_integral_value(rounding=ROUND_CEILING)
    return steps * ROUNDING_STEP


def console_url(service_code: str, quota_code: str, region_id: str | None) -> str:
    """Where a person goes to make the request.

    A global quota gets the host with no region in it, which resolves to whatever region the
    console is already showing. Putting a region in that link would mean choosing one here,
    and a hardcoded region is what the project forbids for a reason: it is an assumption that
    breaks only where being wrong costs the most.
    """
    # The two hosts below are the AWS console, which is a link a person clicks and not an
    # endpoint this product calls. The hardcoding check exists so an outbound call is
    # reviewable, and there is no call here. Making it configurable would be worse than
    # pointless: it would let whoever edits a setting redirect a reader to a host of their
    # choosing, at the moment that reader is about to sign in and change a limit. That is a
    # phishing vector rather than a deployment need.
    regional = "https://{region}.console.aws.amazon.com"  # allow-hardcoded: a link, not a call
    everywhere = "https://console.aws.amazon.com"  # allow-hardcoded: a link, not a call
    host = regional.format(region=region_id) if region_id else everywhere
    return f"{host}/servicequotas/home/services/{service_code}/quotas/{quota_code}"


def cli_command(service_code: str, quota_code: str, region_id: str | None, value: Decimal) -> str:
    """The exact command, ready to paste.

    The subcommand is the CLI spelling of the API this product does not call, and that is not
    an evasion: the two are different acts under different credentials, and they are spelled
    differently so a test can hold the second one absent.

    `--region` is omitted for a global quota rather than guessed at, so the command runs
    against whatever region the caller has configured.
    """
    parts = [
        "aws service-quotas request-service-quota-increase",
        f"--service-code {service_code}",
        f"--quota-code {quota_code}",
        f"--desired-value {value.normalize():f}",
    ]
    if region_id:
        parts.append(f"--region {region_id}")
    return " ".join(parts)


def draft_for(
    *,
    service_code: str,
    quota_code: str,
    region_id: str | None,
    current_limit: Decimal | None,
    observed_usage: Decimal | None,
    is_adjustable: bool,
) -> IncreaseDraft | DraftRefused:
    """A draft, or the reason there is not one.

    Four refusals, ordered by what a reader can do about them. A hard limit is first because
    no amount of measurement changes it.
    """
    if not is_adjustable:
        return DraftRefused(reason=NOT_ADJUSTABLE)
    if observed_usage is None:
        return DraftRefused(reason=NOT_MEASURED)
    if current_limit is None:
        return DraftRefused(reason=NO_LIMIT)

    suggested = suggested_value(observed_usage)
    if suggested <= current_limit:
        return DraftRefused(reason=ALREADY_ROOMY)

    target = (TARGET_HEADROOM * 100).normalize()
    return IncreaseDraft(
        service_code=service_code,
        quota_code=quota_code,
        region_id=region_id,
        current_limit=current_limit,
        observed_usage=observed_usage,
        suggested_value=suggested,
        working=(
            f"The observed peak is {observed_usage.normalize():f} against a limit of "
            f"{current_limit.normalize():f}. Leaving {target:f} percent headroom above that "
            f"peak needs {suggested.normalize():f}, rounded up to the nearest "
            f"{ROUNDING_STEP.normalize():f}. Meter does not submit this."
        ),
        console_url=console_url(service_code, quota_code, region_id),
        cli_command=cli_command(service_code, quota_code, region_id, suggested),
    )
