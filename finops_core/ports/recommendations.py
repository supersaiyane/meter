"""Reading what somebody else already worked out.

AWS produces rightsizing, idle, Graviton and commitment recommendations through
three separate services, and every one of them is better at its own corner than we
would be. This port reads them; `finops_query.waste` covers what they are blind to.

**One method per service, not one method returning everything.** Compute Optimizer
needs an organization level opt in, Trusted Advisor needs a support tier, and Cost
Optimization Hub needs neither. A single method would have to decide what to do
when one of the three refuses, and the honest answer differs per caller: a
collector wants the other two, a contract test wants the refusal. Three methods let
each raise its own typed cause.

**`NotOptedIn` is an expected state here, not a fault.** An estate that has never
enabled Compute Optimizer reports no recommendations from it, and that must reach
a screen as "not opted in, here is how" rather than as "no waste found". Those are
opposite claims and the second one is the comfortable lie.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from finops_core.domain.waste import Recommendation


@runtime_checkable
class RecommendationSource(Protocol):
    """What the provider already knows is wasteful."""

    def compute_optimizer(self) -> Iterable[Recommendation]:
        """Rightsizing and idle findings for compute, from Compute Optimizer.

        Raises:
            NotOptedIn: The organization has never enabled it. ISS-004. An
                expected state, and distinct from an estate with no waste.
            AccessDenied: The role cannot read it.
            Throttled: The provider rejected the read rate.
            Unreachable: The endpoint did not answer.
        """
        ...

    def cost_optimization_hub(self) -> Iterable[Recommendation]:
        """Consolidated findings across the organization, already deduplicated.

        Raises:
            NotOptedIn: The hub has never been enabled for this payer.
            AccessDenied, Throttled, Unreachable: As above.
        """
        ...

    def trusted_advisor(self) -> Iterable[Recommendation]:
        """Idle and underused resources, and the limit checks.

        Raises:
            NotOptedIn: The support tier does not include these checks. OPEN-03.
                Not an error: a Developer tier account is correctly configured and
                simply has fewer signals.
            AccessDenied, Throttled, Unreachable: As above.
        """
        ...
