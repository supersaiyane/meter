"""An answer that cannot hold a figure it did not cite.

P7 spec section 5.2, ADR-0007 made mechanical. An `Answer` is prose with
placeholders and a tuple of `Citation`. The prose holds no numeral at all: a figure
is a placeholder, and the value behind it is read out of a tool result, never out
of what the model wrote. A model that invents a number therefore has nowhere to put
it, and the failure that remains is a wrong sentence beside right numbers, which a
reader can catch.

**Why the entity enforces this, not only the loop.** `finops_query/insight.py`
checks every answer too, and a future route that builds an `Answer` itself would
bypass that check. Constraint 11's reasoning applies to an object as it does to a
table: if application code is the only thing preventing a bad value, the bad value
eventually exists.

**A numeral is any numeric character,** not only the ten ASCII digits. A model that
writes a figure in another script, or as a superscript or a vulgar fraction, has
still written a figure. Spelled out figures are refused too, because the spec's own
example of the failure is "about forty thousand dollars", which contains no digit.
The spelled list leaves out "one", which reads as a pronoun far more often than as
a count ("one of the accounts", "no one"). That gap is the residual risk, and it is
recorded in FEAT-038 rather than hidden.

**Answer, refusal and failure are three types.** Not one type with a nullable field.
A refusal is a first class result with its own reason, spec section 5.3, and a
reader who sees one has learned something true about the product.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from finops_core.constants import REASON_MIN_LENGTH
from finops_core.errors import CollectionError

#: `{{name}}`. The name may hold digits, because they are inside the placeholder and
#: say nothing about a value.
PLACEHOLDER = re.compile(r"\{\{([a-z][a-z0-9_]{0,31})\}\}")
PLACEHOLDER_NAME = re.compile(r"[a-z][a-z0-9_]{0,31}")

#: Figures written as words. Plurals are caught by stripping one trailing "s".
SPELLED_FIGURES = frozenset(
    {
        "zero",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
        "thirty",
        "forty",
        "fifty",
        "sixty",
        "seventy",
        "eighty",
        "ninety",
        "hundred",
        "thousand",
        "million",
        "billion",
        "trillion",
        "dozen",
        "half",
        "twice",
    }
)

_WORD = re.compile(r"[^\W\d_]+")


class ProvenanceError(ValueError):
    """An answer that would put an unattributed figure in front of a reader."""


class Provenance(StrEnum):
    """Two, and only two. A cited figure was measured or it was modelled.

    There is no forecast member, on purpose. ADR-0015 governs forecasts and spec
    section 3 says the assistant does not make one, so a forecast figure has no
    value here to be cited under.
    """

    MEASURED = "measured"
    MODELLED = "modelled"


class Gap(StrEnum):
    """What a refusal says is missing. Spec section 5.3."""

    #: No tool answers the question, so no route does either.
    TOOL = "tool"
    #: The tool answered and the figure is not there, with the row's own reason.
    FIGURE = "figure"
    #: The asker cannot see it.
    SCOPE = "scope"
    #: The tenant's token budget for the month is spent. TASK-P7-007.
    BUDGET = "budget"
    #: The question carried a secret, so it was not sent. TASK-P7-013.
    SECRET = "secret"


class Outcome(StrEnum):
    """The three states of spec section 5.3, as `assistant_exchange.outcome` holds them."""

    ANSWERED = "ANSWERED"
    REFUSED = "REFUSED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class Citation:
    """Where one figure in an answer came from.

    `value` is a Decimal for a figure and a string for a label, such as a service or
    a region whose name holds digits and so could not sit in the prose either.
    """

    placeholder: str
    tool: str
    call_id: str
    field: str
    value: Decimal | str
    provenance: Provenance
    as_of: datetime

    def __post_init__(self) -> None:
        if not PLACEHOLDER_NAME.fullmatch(self.placeholder):
            raise ProvenanceError(f"placeholder {self.placeholder!r} is not a plain name")
        for name in ("tool", "call_id", "field"):
            if not str(getattr(self, name)).strip():
                raise ProvenanceError(f"a citation without its {name} cannot be traced")
        if not isinstance(self.provenance, Provenance):
            raise ProvenanceError(
                f"{self.placeholder} carries no measured or modelled flag, so a reader "
                f"cannot tell what kind of number it is"
            )
        _check_value(self.placeholder, self.value)
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ProvenanceError(f"{self.placeholder} has an as_of with no time zone")

    @property
    def is_figure(self) -> bool:
        return isinstance(self.value, Decimal)

    def as_record(self) -> dict[str, str]:
        """The citation as it is stored and sent. A figure travels as text, so a Decimal
        comes back out of JSON as the figure that was cited rather than a float's idea of it."""
        return {
            "placeholder": self.placeholder,
            "tool": self.tool,
            "call_id": self.call_id,
            "field": self.field,
            "value": str(self.value),
            "kind": "figure" if self.is_figure else "label",
            "provenance": self.provenance.value,
            "as_of": self.as_of.isoformat(),
        }


def _check_value(placeholder: str, value: object) -> None:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ProvenanceError(f"{placeholder} is not a finite figure")
        return
    if isinstance(value, str):
        if not value.strip():
            raise ProvenanceError(f"{placeholder} cites an empty label")
        return
    raise ProvenanceError(
        f"{placeholder} holds a {type(value).__name__}. A figure is a Decimal, because a "
        f"float is wrong in the last places and a figure that does not reconcile is not "
        f"trusted twice."
    )


def bare_figures(prose: str) -> tuple[str, ...]:
    """Every figure in the prose that no placeholder put there, in order."""
    outside = PLACEHOLDER.sub(" ", prose)
    numerals = [character for character in outside if character.isnumeric()]
    spelled = [
        word
        for word in _WORD.findall(outside.lower())
        if word in SPELLED_FIGURES or word.removesuffix("s") in SPELLED_FIGURES
    ]
    return (*numerals, *spelled)


def check_prose(prose: str) -> None:
    """Refuse prose holding a figure no placeholder put there.

    One check for every sentence a model writes that a reader will see: an answer's
    prose, and a refusal in the model's own words, which could otherwise carry the
    estimate it was declining to give.

    Raises:
        ProvenanceError: Counting the figures, never repeating them. The message becomes
            a stored failure detail, and a figure the model wrote may be the digits of a
            secret it was asked to echo.
    """
    uncited = bare_figures(prose)
    if uncited:
        raise ProvenanceError(
            f"the prose holds figures no citation placed, {len(uncited)} of them, not "
            f"repeated here because one may be part of a secret"
        )


@dataclass(frozen=True)
class Answer:
    """Prose with placeholders, and the citation behind every one."""

    prose: str
    citations: tuple[Citation, ...]

    def __post_init__(self) -> None:
        if not self.prose.strip():
            raise ProvenanceError("an answer with no prose answers nothing")
        check_prose(self.prose)
        outside = PLACEHOLDER.sub("", self.prose)
        if "{" in outside or "}" in outside:
            raise ProvenanceError(
                "the prose holds a brace outside a placeholder, which would reach the "
                "reader as a broken figure"
            )
        names = [citation.placeholder for citation in self.citations]
        if len(names) != len(set(names)):
            raise ProvenanceError("two citations claim one placeholder")
        used = set(PLACEHOLDER.findall(self.prose))
        missing = sorted(used - set(names))
        if missing:
            raise ProvenanceError(f"placeholders with no citation: {', '.join(missing)}")
        unused = sorted(set(names) - used)
        if unused:
            raise ProvenanceError(f"citations no placeholder uses: {', '.join(unused)}")


@dataclass(frozen=True)
class Refusal:
    """The question is understood and the product cannot answer it. Says what is missing."""

    gap: Gap
    reason: str
    #: The screen that would show the missing thing once the gap closes, if one does.
    screen: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.gap, Gap):
            raise ValueError("a refusal names what kind of thing is missing")
        if len(self.reason.strip()) < REASON_MIN_LENGTH:
            raise ValueError(
                f"a refusal's reason is a sentence of at least {REASON_MIN_LENGTH} characters, "
                f"because one that says only 'cannot answer' teaches the reader nothing"
            )
        if self.screen is not None and (not self.screen.startswith("/") or " " in self.screen):
            raise ValueError(f"{self.screen!r} is not a screen path")


#: The seven typed causes by name, as the database and the wire carry them.
CAUSES = frozenset(cause.__name__ for cause in CollectionError.__subclasses__())


@dataclass(frozen=True)
class Failure:
    """The exchange could not complete. One of the seven typed causes, never a generic one."""

    cause: str
    detail: str

    def __post_init__(self) -> None:
        if self.cause not in CAUSES:
            raise ValueError(f"{self.cause!r} is not one of {', '.join(sorted(CAUSES))}")

    @classmethod
    def from_error(cls, error: CollectionError) -> Failure:
        return cls(cause=error.cause, detail=error.detail or error.remediation)
