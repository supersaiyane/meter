"""The closed set of reasons a collection can fail.

Constraint 5 in CLAUDE.md: partial failure is first class, causes are typed,
and a failure is never rendered as the number zero. This module is where that
constraint becomes code.

There are exactly six causes and there is deliberately no generic one. ISS-015
records why: the moment a catch all exists, the cheapest thing an author can do
at every future call site is reach for it, and within one release every failure
is generic again. The taxonomy then describes nothing and the interface is back
to showing a confident number over an unknown problem.

`CollectionError` exists only so the six can be enumerated and caught together.
It refuses to be constructed, which is what keeps it from becoming the catch
all by another name. `tests/core/test_errors.py` asserts both the membership of
the set and the absence of a second level below it.

`NoData` is the one cause whose documented rendering is a zero, because it is
the one case where zero is the truth rather than a mask over a failure.
"""

from __future__ import annotations

from typing import ClassVar


class CollectionError(Exception):
    """Abstract parent of the six causes. Never raised, never constructed."""

    cause: ClassVar[str] = "CollectionError"
    renders_as_zero: ClassVar[bool] = False
    remediation_text: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: object) -> None:
        # The cause travels to the database and to the wire, so deriving it
        # from the type name is what stops the two drifting apart.
        super().__init_subclass__(**kwargs)
        cls.cause = cls.__name__

    def __init__(self, *, scope_key: str, collector: str, detail: str = "") -> None:
        if type(self) is CollectionError:
            raise TypeError(
                "CollectionError is abstract and must never be raised. Choose one of "
                "AccessDenied, Throttled, NotOptedIn, NoData, Unreachable or SchemaDrift. "
                "See ISS-015."
            )
        self.scope_key = scope_key
        self.collector = collector
        self.detail = detail
        super().__init__(str(self))

    @property
    def remediation(self) -> str:
        """What the person reading the failure should actually do next."""
        return self.remediation_text

    def __str__(self) -> str:
        tail = f": {self.detail}" if self.detail else ""
        return f"{self.cause} in {self.collector} for {self.scope_key}{tail}"


class AccessDenied(CollectionError):
    """The credential was refused, so the answer is unknown rather than zero."""

    remediation_text = (
        "The member account role is missing, or its trust policy does not admit the hub. "
        "Check the StackSet deployment for this account, then re run the collector."
    )


class Throttled(CollectionError):
    """The provider rejected the call rate."""

    remediation_text = (
        "The provider rejected the call rate. The run retries with backoff. If it keeps "
        "happening, lower the collector concurrency in configuration rather than in code."
    )


class NotOptedIn(CollectionError):
    """The service exists but this organization has never enabled it."""

    remediation_text = (
        "The service is not enabled for this account or organization. Enable it at the "
        "organization level, then re run the collector."
    )


class NoData(CollectionError):
    """The source holds nothing for this scope and period, and that is the truth."""

    renders_as_zero = True
    remediation_text = (
        "The source holds no rows for this scope and period. This is a true zero rather "
        "than a failure, and it is the only cause that may be drawn as one."
    )


class Unreachable(CollectionError):
    """The endpoint did not answer at all."""

    remediation_text = (
        "The provider endpoint did not answer. Check network egress and any endpoint "
        "override, then re run the collector."
    )


class SchemaDrift(CollectionError):
    """The response did not match the shape this adapter expects."""

    remediation_text = (
        "The response did not match the shape this adapter expects, so the value was not "
        "trusted. An unrecognised provider error code is mapped here on purpose, because "
        "guessing quietly is how a wrong number ships. Read the detail and update the adapter."
    )
