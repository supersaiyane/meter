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


class Misconfigured(CollectionError):
    """A value this deployment set is wrong, and no retry will change that.

    The seventh cause, added 2026-09-28 under ADR-0026 and recorded as ISS-215. Before it, a
    configuration aggregator name that does not exist and a state file path that does not exist
    both arrived as `SchemaDrift`, which is loud and is never a zero, so nothing was hidden. It
    was still the wrong word: it told an operator their schema had drifted and sent them to look
    for an API change, when the fix was one line of their own settings.

    **The test for this cause is whether a person can fix it by editing configuration.** Not
    whether the provider said "not found": a bucket we were told to read and cannot is
    misconfigured, and an account that genuinely holds no budgets is `NoData`. Not whether the
    call failed for a reason we did not expect either, because that is what `SchemaDrift` is for
    and the two must not blur: one says the operator is wrong and the other says we are.

    It is deliberately not retried. Every other non fatal cause here is worth another attempt on
    the next cadence; this one produces the identical failure forever until somebody changes a
    setting, so retrying it only fills the error table.
    """

    remediation_text = (
        "A value this deployment is configured with does not exist at the provider, so the "
        "collector could not read anything. This is not a transient failure and will not "
        "recover on its own. Read the detail for the name that was rejected, correct it in "
        "configuration, then re run the collector."
    )


class SchemaDrift(CollectionError):
    """The response did not match the shape this adapter expects."""

    remediation_text = (
        "The response did not match the shape this adapter expects, so the value was not "
        "trusted. An unrecognised provider error code is mapped here on purpose, because "
        "guessing quietly is how a wrong number ships. Read the detail and update the adapter."
    )
