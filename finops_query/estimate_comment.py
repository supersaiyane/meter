"""An estimate as the one comment on its pull request. TASK-P16-006, FEAT-096, spec section 5.5.

OPEN-45, answered by the owner on 2026-10-16: one comment per pull request and folder, edited in
place, blocking nothing. The comment opens with a marker naming the folder, so the next plan for a
newer commit finds it again. It says first how many resources are not priced, so the figure is never
read as the whole; then the monthly figures before, after and the change; a line per priced
resource; every one not priced with its reason; the notes; and what every figure rests on.

**List prices only.** Every figure here is modelled from AWS's published prices. Nothing from the
bill is written into a repository, so a reader of the pull request learns nothing of the
organization's spend.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

#: GitHub refuses a comment over 65,536 characters; the comment stops well short of it.
MOST: Final = 60_000
#: The most resources listed in each part before the rest are counted rather than listed.
LISTED: Final = 200
ACTIONS: Final = {
    ("create",): "create",
    ("update",): "change",
    ("delete",): "destroy",
    ("delete", "create"): "replace",
    ("create", "delete"): "replace",
}
TABLE: Final = (
    "| Resource | Action | Before | After | Change |",
    "| --- | --- | ---: | ---: | ---: |",
)


@dataclass(frozen=True)
class CommentLine:
    """One change as the comment shows it."""

    address: str
    actions: tuple[str, ...]
    monthly_before: Decimal | None
    monthly_after: Decimal | None
    reason: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommentedEstimate:
    """What the comment is written from: one plan's estimate, its commit and its folder."""

    folder: str
    head_sha: str
    monthly_before: Decimal
    monthly_after: Decimal
    monthly_change: Decimal
    lines: tuple[CommentLine, ...]
    #: The catalog versions the figures were read from.
    versions: tuple[str, ...]
    priced_at: datetime


def marker(folder: str) -> str:
    """The first line of Meter's comment for a folder, by which it is found again."""
    return f"<!-- meter:estimate folder={folder or '.'} -->"


def render(estimate: CommentedEstimate) -> str:
    """The comment, in GitHub's Markdown, never longer than GitHub accepts."""
    priced = [one for one in estimate.lines if one.reason is None]
    unpriced = [one for one in estimate.lines if one.reason is not None]
    parts = [
        marker(estimate.folder),
        f"### Meter: what this change costs a month, `{estimate.folder or '.'}`",
        "",
        _headline(len(unpriced), len(estimate.lines)),
        "",
        "| Before | After | Change |",
        "| ---: | ---: | ---: |",
        f"| {_usd(estimate.monthly_before)} | {_usd(estimate.monthly_after)} "
        f"| **{_signed(estimate.monthly_change)} USD** |",
    ]
    if priced:
        parts += ["", *TABLE, *(_row(one) for one in priced[:LISTED]), *_more(len(priced))]
    if unpriced:
        parts += ["", "**Not priced**", ""]
        parts += [f"- `{_cell(one.address)}`: {one.reason}" for one in unpriced[:LISTED]]
        parts += _more(len(unpriced))
    notes = [(one.address, note) for one in priced for note in one.notes]
    if notes:
        parts += ["", "<details><summary>Notes</summary>", ""]
        parts += [f"- `{_cell(address)}`: {note}" for address, note in notes[:LISTED]]
        parts += [*_more(len(notes)), "", "</details>"]
    parts += ["", _footing(estimate)]
    body = "\n".join(parts) + "\n"
    return body if len(body) <= MOST else _cut(body)


def _headline(unpriced: int, lines: int) -> str:
    if lines == 0:
        return "This plan changes nothing Meter prices."
    if unpriced == 0:
        return f"Every one of the {lines} resources this plan changes is priced."
    verb, pronoun = ("is", "it") if unpriced == 1 else ("are", "them")
    return (
        f"**{unpriced} of {lines} resources {verb} not priced**, so the figures below leave "
        f"{pronoun} out. Each is listed with the reason."
    )


def _row(line: CommentLine) -> str:
    before, after = line.monthly_before, line.monthly_after
    change = (after or Decimal(0)) - (before or Decimal(0))
    action = ACTIONS.get(line.actions, "/".join(line.actions))
    return (
        f"| `{_cell(line.address)}` | {action} | {_amount(before)} | {_amount(after)} "
        f"| {_signed(change)} |"
    )


def _more(count: int) -> list[str]:
    if count <= LISTED:
        return []
    return [f"- and {count - LISTED} more, on Meter's Estimates screen"]


def _footing(estimate: CommentedEstimate) -> str:
    held = sorted(set(estimate.versions))
    versions = ", ".join(held) or "none read"
    when = estimate.priced_at.strftime("%Y-%m-%d %H:%M UTC")
    return (
        "Modelled from AWS's on demand list prices, 730 hours a month, in USD, price list "
        f"{'versions' if len(held) > 1 else 'version'} {versions}. Commitment discounts are not "
        f"applied. Commit `{estimate.head_sha[:12]}`, priced {when}."
    )


def _cut(body: str) -> str:
    """A comment GitHub would refuse, cut at a line and said to be cut."""
    note = "\n\nThe rest is on Meter's Estimates screen.\n"
    kept = body[: MOST - len(note)]
    return kept[: kept.rfind("\n")] + note


def _cell(text: str) -> str:
    """Text inside a table cell or code span, its pipes and backticks made harmless."""
    return text.replace("|", "\\|").replace("`", "'")


def _amount(amount: Decimal | None) -> str:
    return "" if amount is None else f"{amount:,.2f}"


def _usd(amount: Decimal) -> str:
    return f"{amount:,.2f} USD"


def _signed(amount: Decimal) -> str:
    sign = "+" if amount > 0 else ""
    return f"{sign}{amount:,.2f}"
