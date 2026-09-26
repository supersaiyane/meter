"""Reading which resources infrastructure as code owns.

FEAT-057, TASK-P4-013.

**The location is configuration, never discovery.** A port that searched for state files would
be enumerating buckets, and enumerating somebody's buckets to see what is in them is
reconnaissance whatever the intent. An operator names the backends; Meter reads those and
nothing else. That is also why a missing backend is a configuration gap a screen can report
rather than a silence.

**Read only, constraint 6.** State is read. Nothing here writes, locks, or takes a lease, which
matters more than usual: acquiring a Terraform state lock would block whoever was mid apply,
and a tool that can stall somebody's deployment is not read only in any sense they care about.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from finops_core.domain.iac import StateRead


@runtime_checkable
class StateSource(Protocol):
    """Reads the resources named by the configured infrastructure as code state."""

    def read(self, locations: Iterable[str]) -> StateRead:
        """Every resource the given state locations own, and the ones that refused.

        Does not raise for a location it could not read. The refusal is on the `StateRead`,
        with its typed cause, for the same reason `TopologySource.read_slice` reports rather
        than raising: a caller handed an exception has to choose between discarding the
        resources it did find and pretending the read was whole, and both are wrong.

        It does raise where no location could be read at all, because that is a configuration
        failure rather than a partial answer, and a run that wrote nothing while reporting
        success is the failure this whole sub project exists to prevent.

        Raises:
            Unreachable: No configured location could be reached.
            AccessDenied: The session may not read any configured location.
        """
        ...

    @property
    def locations(self) -> tuple[str, ...]:
        """The configured locations, so a caller can report the denominator.

        On the port rather than left to the caller, because "we read three of four backends" is
        the sentence a screen needs and a caller that had to count them itself would be the
        second place that number is decided.
        """
        ...
