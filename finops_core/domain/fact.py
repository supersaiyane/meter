"""What every fact in this system has to be able to say about itself.

Constraint 4 in CLAUDE.md: every fact carries `as_of`. Constraint 10: two
timestamps, because `as_of` is when the value was true at the source and
`collected_at` is when Meter fetched it, and conflating them makes a stale
number look fresh.

Those two constraints are a shared base class rather than a convention repeated
in seven modules, because a convention repeated in seven modules is a
convention that will be missing from the eighth. Inheriting from `Fact` is what
puts an entity in `tests/core/test_domain.py::test_as_of_is_required`, so a new
fact without its timestamps fails the build rather than reaching a screen.

`IngestRun` deliberately does not inherit from this. A run is a record of our
own work, not a fact about a cloud, and its timestamps are `started_at` and
`finished_at`. Giving it an `as_of` would invite the question of what the value
means, and the honest answer is nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, kw_only=True)
class Fact:
    """A value that was true somewhere, at a time, and was read at another time."""

    #: When the value was true at the source.
    as_of: datetime
    #: When Meter fetched it. Never earlier than `as_of`.
    collected_at: datetime
