"""How much of the organization a view actually covers. ISS-016.

Entitlement based visibility silently makes organization totals partial. A user
entitled to two of five accounts asks for total cost, gets the sum of two, and
there is nothing on the page saying so. The number is not wrong in itself and
that is exactly the problem: it is a true answer to a question nobody asked.

Coverage is visible over the total number of accounts in the organization,
never visible over visible. The second is the bug ISS-016 describes and it
always reports full coverage, which is why it survives review.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeCoverage:
    """Visible accounts against every account the organization holds."""

    visible: int
    total: int

    def __post_init__(self) -> None:
        if self.visible > self.total:
            raise ValueError(
                f"Coverage cannot exceed the organization: {self.visible} visible of "
                f"{self.total}. A total smaller than the visible count means the total "
                f"was computed from the visible set, which is ISS-016 itself."
            )
        if self.visible < 0 or self.total < 0:
            raise ValueError("Coverage counts cannot be negative")

    @property
    def is_partial(self) -> bool:
        """True when the figures on the page describe part of the organization."""
        return self.visible < self.total

    @property
    def fraction(self) -> float:
        """Visible share, between 0 and 1. An empty organization is fully covered."""
        if self.total == 0:
            return 1.0
        return self.visible / self.total

    def as_dict(self) -> dict[str, object]:
        """The shape every API response carries alongside its numbers."""
        return {
            "visible": self.visible,
            "total": self.total,
            "is_partial": self.is_partial,
        }
