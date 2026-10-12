"""What AI spend bought: cost by model, token, feature and caller, and GPU use. FEAT-081 to 085.

P13 spec section 5.7, TASK-P13-007. Pure arithmetic over what the collectors stored, so the routes
only read and shape. Three readings, each saying how every figure was arrived at:

- **Spend**: the AI lines of the bill, the cloud's and the AI providers' own, grouped by provider,
  model, token type, feature or caller. Cost is measured. Tokens are measured where the bill line
  counts them, which a cloud bill's model lines do; where it does not, which the providers' own
  cost reports do not, they are read from the same provider's usage report for the same day,
  model, token type and project, and a cost per token from them is modelled, because the two
  figures come from two reports. Requests come only from usage reports and invocation logs, so a
  cost per request is always modelled.
- **Callers**: each caller's tokens from the usage reports and invocation logs, priced at the unit
  cost the bill shows for the same source, account, model, token type and day. Modelled, always: a
  bill names a role, and the price a role paid is spread over the callers who used it.
- **GPU**: each accelerated instance's hours and cost from the bill, and how busy it was from the
  agent's metrics, or not published, never nought percent.

ADR-0028: nothing here names a vendor. A usage source is matched to the bill through the sources
the tenant connected: a connected provider bills itself, and any other source is billed through
the cloud bill.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Final

from finops_core.domain.ai import accelerated_instance_type

#: The cloud bill's own lines, as `cost_focus_daily.ingest_source` names them.
CLOUD_BILL: Final = "aws_export"
MEASURED: Final = "measured"
MODELLED: Final = "modelled"
#: What a group is called when its lines do not say.
UNNAMED: Final = "(not named)"
NOT_TOKENS: Final = "(not tokens)"
SEVERAL: Final = "(several)"
#: A workspace the provider reports with no id, its default.
DEFAULT_WORKSPACE: Final = "(default workspace)"
#: What a resource id carries when it names an application inference profile.
PROFILE: Final = "application-inference-profile/"
#: Tokens are priced per thousand on the screen, the unit every provider's price list uses.
PER: Final = Decimal(1000)
#: How finely a derived figure is kept: a millionth of a dollar.
PLACES: Final = Decimal("0.000001")

GROUPS: Final = ("provider", "model", "token_type", "feature", "caller")

#: The parts of a model's name that differ between a bill and a log for the same model: a cross
#: Region prefix, a publisher before the first dot, a version and a date.
_REGION_PREFIX: Final = re.compile(r"^(us|eu|apac|global|us-gov|ca|jp|au)\.")
_PUBLISHER: Final = re.compile(r"^[a-z][a-z0-9-]*\.(?=[a-z])")
_VERSION: Final = re.compile(r"-v\d+(:\d+)?$")
_DATED: Final = re.compile(r"-(\d{8}|\d{4}-\d{2}-\d{2})$")
_NOT_ALPHANUMERIC: Final = re.compile(r"[^a-z0-9]")

Key = tuple[str, ...]


def model_key(name: str | None) -> str:
    """One spelling of a model for matching, whichever report named it.

    A bill names a model in its usage type, `ClaudeSonnet4`; an invocation log names it by its
    identifier, `publisher.claude-sonnet-4-20250514-v1:0`, or by an ARN ending in one. Both come
    to `claudesonnet4`. A version written with a dot, `Claude3.7Sonnet`, is not a publisher.
    """
    if not name:
        return ""
    text = name.strip().lower().rsplit("/", 1)[-1]
    text = _REGION_PREFIX.sub("", text)
    text = _PUBLISHER.sub("", text)
    text = _VERSION.sub("", text)
    text = _DATED.sub("", text)
    return _NOT_ALPHANUMERIC.sub("", text)


@dataclass(frozen=True, kw_only=True)
class Line:
    """One AI line of the bill, as the spend reading needs it."""

    source: str
    provider: str
    account: str
    #: The Region for a cloud bill line, as the invocation logs record it; the project or
    #: workspace for a provider's, which the bill holds as its sub account.
    workspace: str | None
    day: date
    model: str | None
    token_type: str | None
    tokens: Decimal | None
    caller: str | None
    resource_id: str | None
    tags: Mapping[str, str]
    cost: Decimal
    as_of: datetime
    collected_at: datetime


@dataclass(frozen=True, kw_only=True)
class Usage:
    """One day of one caller's tokens and requests, from a usage report or invocation logs."""

    source: str
    account: str
    workspace: str
    day: date
    model: str
    caller: str
    application: str
    tokens: Mapping[str, int]
    requests: int | None


@dataclass(frozen=True, kw_only=True)
class SpendRow:
    name: str
    provider: str
    cost: Decimal
    tokens: Decimal | None
    tokens_basis: str | None
    requests: int | None
    cost_per_1k_tokens: Decimal | None
    cost_per_1k_tokens_basis: str | None
    cost_per_request: Decimal | None
    cost_per_request_basis: str | None


@dataclass(frozen=True, kw_only=True)
class CallerRow:
    source: str
    account: str
    caller: str
    application: str
    model: str
    tokens: int
    requests: int | None
    #: Modelled, always: the bill's unit cost spread over this caller's tokens. None where the bill
    #: holds no priced token for the model and day, which is unknown and never free.
    modelled_cost: Decimal | None


@dataclass(frozen=True, kw_only=True)
class GpuLine:
    """One billed line of an instance whose usage type may be accelerated."""

    account: str
    region: str | None
    instance_id: str | None
    usage_type: str | None
    day: date
    hours: Decimal | None
    cost: Decimal


@dataclass(frozen=True, kw_only=True)
class GpuDay:
    """One published day of an instance's accelerators."""

    account: str
    instance_id: str
    day: date
    average_percent: Decimal
    peak_percent: Decimal


@dataclass(frozen=True, kw_only=True)
class GpuRow:
    account: str
    region: str | None
    instance_id: str
    instance_type: str
    hours: Decimal
    cost: Decimal
    days_billed: int
    days_published: int
    #: The mean of the published days' averages and the highest peak; None where none published.
    average_percent: Decimal | None
    peak_percent: Decimal | None


@dataclass
class _Group:
    """One group's sums while the lines are read. Each count is None until a line gives it."""

    providers: set[str] = field(default_factory=set)
    cost: Decimal = Decimal(0)
    billed: Decimal | None = None
    reported: Decimal | None = None
    requests: Decimal | None = None


def feature_of(line: Line, tag_key: str) -> str:
    """What application a line belongs to: a tag the deployment names, an application inference
    profile, a provider's project or workspace, or not named."""
    if tag_key and line.tags.get(tag_key):
        return line.tags[tag_key]
    if line.resource_id and PROFILE in line.resource_id:
        return line.resource_id.rsplit(PROFILE, 1)[1] or UNNAMED
    if line.source != CLOUD_BILL:
        return line.workspace or DEFAULT_WORKSPACE
    return UNNAMED


def bill_source(usage_source: str, self_billed: Iterable[str]) -> str:
    """The bill a usage source's cost is on: its own, if it bills itself, else the cloud's."""
    return usage_source if usage_source in set(self_billed) else CLOUD_BILL


# -- spend ------------------------------------------------------------------------------------


def spend(
    lines: Sequence[Line],
    usage: Sequence[Usage],
    group_by: str,
    *,
    tag_key: str = "",
    self_billed: Iterable[str] = (),
) -> list[SpendRow]:
    """The bill's AI lines grouped, worst first, each figure with how it was arrived at."""
    if group_by not in GROUPS:
        raise ValueError(f"cannot group AI spend by {group_by!r}")
    reported, requested = _reported(usage, set(self_billed))
    token_share = _shares(lines, _token_key)
    request_share = _shares(lines, _request_key)
    groups: dict[str, _Group] = defaultdict(_Group)
    for index, line in enumerate(lines):
        group = groups[_name(line, group_by, tag_key)]
        group.providers.add(line.provider)
        group.cost += line.cost
        if line.tokens is not None:
            group.billed = (group.billed or Decimal(0)) + line.tokens
        elif line.token_type and _token_key(line) in reported:
            found = reported[_token_key(line)] * token_share[index]
            group.reported = (group.reported or Decimal(0)) + found
        if _request_key(line) in requested:
            counted = requested[_request_key(line)] * request_share[index]
            group.requests = (group.requests or Decimal(0)) + counted
    rows = [_row(name, group) for name, group in groups.items()]
    return sorted(rows, key=lambda row: (-row.cost, row.name))


def _name(line: Line, group_by: str, tag_key: str) -> str:
    if group_by == "provider":
        return line.provider
    if group_by == "model":
        return line.model or UNNAMED
    if group_by == "token_type":
        return line.token_type or NOT_TOKENS
    if group_by == "feature":
        return feature_of(line, tag_key)
    return line.caller or UNNAMED


def _request_key(line: Line) -> Key:
    """What ties a line to the requests counted for it: source, account, workspace, model, day."""
    return (
        line.source,
        line.account,
        line.workspace or "",
        model_key(line.model),
        line.day.isoformat(),
    )


def _token_key(line: Line) -> Key:
    """What ties a line to the tokens a usage report counted for it: the request key and type."""
    return (*_request_key(line), line.token_type or "")


def _shares(lines: Sequence[Line], key_of: Callable[[Line], Key]) -> list[Decimal]:
    """Each line's share, by cost, of the lines that share its key, so a count is not doubled."""
    keyed: dict[Key, list[int]] = defaultdict(list)
    for index, line in enumerate(lines):
        keyed[key_of(line)].append(index)
    share = [Decimal(0)] * len(lines)
    for members in keyed.values():
        total = sum((lines[i].cost for i in members), Decimal(0))
        for i in members:
            share[i] = lines[i].cost / total if total else Decimal(1) / len(members)
    return share


def _reported(
    usage: Sequence[Usage], billers: set[str]
) -> tuple[dict[Key, Decimal], dict[Key, Decimal]]:
    """Tokens by token key and requests by request key, summed over keys and callers."""
    tokens: dict[Key, Decimal] = defaultdict(Decimal)
    requests: dict[Key, Decimal] = defaultdict(Decimal)
    for one in usage:
        source = bill_source(one.source, billers)
        base = (source, one.account, one.workspace, model_key(one.model), one.day.isoformat())
        for token_type, count in one.tokens.items():
            if count:
                tokens[(*base, token_type)] += Decimal(count)
        if one.requests is not None:
            requests[base] += Decimal(one.requests)
    return dict(tokens), dict(requests)


def _row(name: str, group: _Group) -> SpendRow:
    cost, billed, reported, counted = group.cost, group.billed, group.reported, group.requests
    tokens: Decimal | None
    basis: str | None
    if billed is not None:
        tokens = billed + (reported or Decimal(0))
        basis = MEASURED if reported is None else MODELLED
    elif reported is not None:
        tokens, basis = reported, MODELLED
    else:
        tokens, basis = None, None
    per_token = (cost / tokens * PER).quantize(PLACES) if tokens else None
    requests = int(counted.to_integral_value()) if counted is not None else None
    per_request = (cost / requests).quantize(PLACES) if requests else None
    return SpendRow(
        name=name,
        provider=next(iter(group.providers)) if len(group.providers) == 1 else SEVERAL,
        cost=cost,
        tokens=tokens.to_integral_value() if tokens is not None else None,
        tokens_basis=basis,
        requests=requests,
        cost_per_1k_tokens=per_token,
        cost_per_1k_tokens_basis=basis if per_token is not None else None,
        cost_per_request=per_request,
        cost_per_request_basis=MODELLED if per_request is not None else None,
    )


# -- callers ----------------------------------------------------------------------------------


def callers(
    lines: Sequence[Line], usage: Sequence[Usage], *, self_billed: Iterable[str] = ()
) -> list[CallerRow]:
    """Each caller's tokens and requests, priced at the bill's unit cost. Modelled, always."""
    billers = set(self_billed)
    price = _unit_costs(lines, usage, billers)
    grouped: dict[tuple[str, str, str, str, str], list[Usage]] = defaultdict(list)
    for one in usage:
        grouped[(one.source, one.account, one.caller, one.application, one.model)].append(one)
    rows = [_caller(key, used, price, billers) for key, used in grouped.items()]
    return sorted(
        rows,
        key=lambda row: (row.modelled_cost is None, -(row.modelled_cost or 0), -row.tokens),
    )


def _caller(
    key: tuple[str, str, str, str, str],
    used: Sequence[Usage],
    price: Mapping[tuple[str, str, str, date, str], Decimal],
    billers: set[str],
) -> CallerRow:
    source, account, caller, application, model = key
    cost: Decimal | None = Decimal(0)
    for one in used:
        billed = bill_source(one.source, billers)
        for token_type, count in one.tokens.items():
            if not count or cost is None:
                continue
            unit = price.get((billed, one.account, model_key(one.model), one.day, token_type))
            cost = None if unit is None else cost + unit * count
    counts = [one.requests for one in used]
    return CallerRow(
        source=source,
        account=account,
        caller=caller,
        application=application,
        model=model,
        tokens=sum(sum(one.tokens.values()) for one in used),
        requests=None if any(c is None for c in counts) else sum(c or 0 for c in counts),
        modelled_cost=cost.quantize(PLACES) if cost is not None else None,
    )


def _unit_costs(
    lines: Sequence[Line], usage: Sequence[Usage], billers: set[str]
) -> dict[tuple[str, str, str, date, str], Decimal]:
    """What one token cost, by source, account, model, day and token type, from the bill.

    The bill's own token count where it has one; otherwise every token the usage reports counted
    for the same key, so the bill's cost is spread over the tokens it was for.
    """
    cost: dict[tuple[str, str, str, date, str], Decimal] = defaultdict(Decimal)
    billed: dict[tuple[str, str, str, date, str], Decimal] = defaultdict(Decimal)
    for line in lines:
        if not line.token_type:
            continue
        key = (line.source, line.account, model_key(line.model), line.day, line.token_type)
        cost[key] += line.cost
        if line.tokens is not None:
            billed[key] += line.tokens
    used: dict[tuple[str, str, str, date, str], Decimal] = defaultdict(Decimal)
    for one in usage:
        source = bill_source(one.source, billers)
        for token_type, count in one.tokens.items():
            used[(source, one.account, model_key(one.model), one.day, token_type)] += count
    units: dict[tuple[str, str, str, date, str], Decimal] = {}
    for key, spent in cost.items():
        tokens = billed.get(key) or used.get(key)
        if tokens:
            units[key] = spent / tokens
    return units


# -- GPU --------------------------------------------------------------------------------------


def gpu(lines: Sequence[GpuLine], published: Sequence[GpuDay]) -> list[GpuRow]:
    """Each accelerated instance's hours, cost and how busy it was where it said, worst first."""
    billed: dict[tuple[str, str], list[GpuLine]] = defaultdict(list)
    for line in lines:
        if line.instance_id and accelerated_instance_type(line.usage_type):
            billed[(line.account, line.instance_id)].append(line)
    days: dict[tuple[str, str], list[GpuDay]] = defaultdict(list)
    for one in published:
        days[(one.account, one.instance_id)].append(one)
    rows: list[GpuRow] = []
    for (account, instance_id), billed_lines in billed.items():
        billed_days = {one.day for one in billed_lines}
        seen = [one for one in days.get((account, instance_id), []) if one.day in billed_days]
        averages = [one.average_percent for one in seen]
        rows.append(
            GpuRow(
                account=account,
                region=billed_lines[0].region,
                instance_id=instance_id,
                instance_type=accelerated_instance_type(billed_lines[0].usage_type) or "",
                hours=sum((one.hours or Decimal(0) for one in billed_lines), Decimal(0)),
                cost=sum((one.cost for one in billed_lines), Decimal(0)),
                days_billed=len(billed_days),
                days_published=len({one.day for one in seen}),
                average_percent=(
                    (sum(averages, Decimal(0)) / len(averages)).quantize(Decimal("0.01"))
                    if averages
                    else None
                ),
                peak_percent=max((one.peak_percent for one in seen), default=None),
            )
        )
    return sorted(rows, key=lambda row: (-row.cost, row.instance_id))
