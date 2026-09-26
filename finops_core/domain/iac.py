"""Whether infrastructure as code manages a resource, and the three answers to that.

FEAT-057, TASK-P4-013. Adopted from the 2026-09-26 IBM Turbonomic review, which lists
Terraform state discovery as the thing FEAT-040 needs before it can produce a useful pull
request: a remediation that does not know which file to change is a remediation nobody can
apply.

**The whole design is one sentence: reading state tells you what is managed and never what is
not.** A state file names the resources it owns. It does not name the resources it does not
own, and nothing in it says whether it is the only state file in the organization. So a
resource absent from everything we read is a resource we did not find, which is a different
fact from a resource nobody manages.

Those two get conflated by every tool that stores a boolean, and the cost of conflating them
is concrete: `UNMANAGED` tells somebody to import a resource or to write it into code, and
doing that to a resource already inside a module somebody else owns produces a duplicate, a
state conflict, or a second copy of a live resource. "We did not look in the right bucket" is
not an instruction.

**So there are three states and the default is the honest one.**

- `MANAGED`, with the address that owns it. Evidence: we found it.
- `UNMANAGED`, which requires a declaration. An operator has to say that the backends they
  configured are the whole of the infrastructure as code for a set of accounts. Without that
  the absence of a resource from what we read carries no information.
- `NOT_DETERMINED`, the default, and the answer for everything else.

**`UNMANAGED` is a claim about our configuration, not about the cloud.** That is why the
declaration is per account and lives in settings rather than being inferred: an operator who
adds a second Terraform workspace next quarter and does not tell us would otherwise have every
resource in it reported as unmanaged, confidently and wrongly, until somebody acted on one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from finops_core.domain.fact import Fact


class ManagementState(StrEnum):
    """The three answers. `NOT_DETERMINED` is the default and is never inferred away."""

    MANAGED = "MANAGED"
    #: Only where an operator declared the configured backends exhaustive for the account.
    UNMANAGED = "UNMANAGED"
    #: Nothing was read that covers this resource. Not a synonym for unmanaged.
    NOT_DETERMINED = "NOT_DETERMINED"


@dataclass(frozen=True, kw_only=True)
class ManagedResource(Fact):
    """One resource a state file owns, and the address that owns it.

    `address` is the module path and resource name as the state records them, for example
    `module.network.aws_vpc.main`. It is what FEAT-040 needs in order to open a pull request
    against the right block, and it is what a reader needs in order to find the code.
    """

    #: The provider's own identifier, an ARN, which is what `topology_node` keys on. The join
    #: is on this rather than on a node identifier because a state file may own a resource
    #: Meter has never inventoried, and that is worth knowing rather than worth dropping.
    provider_id: str
    address: str
    #: Which state we read it from, so a reader can find the file rather than being told a
    #: resource is managed by something unnamed.
    state_reference: str


@dataclass(frozen=True)
class StateRead:
    """What one read of the configured state found, including what it could not read.

    Modelled on `SliceRead` in `topology.py` and for the same reason: a read that fell short
    returns rather than raising, because a partial answer plus a record of what is missing is
    useful and an exception is not. A caller that got an exception would have to choose between
    discarding the resources it did find and pretending the read was whole.
    """

    managed: tuple[ManagedResource, ...]
    #: The state locations that could not be read, with the typed cause, so a screen can say
    #: which file rather than saying that something went wrong. An empty tuple is a whole read.
    refused: tuple[tuple[str, str], ...] = ()

    @property
    def is_whole(self) -> bool:
        """True where every configured location was read.

        The property that gates `UNMANAGED`. A declaration that the configured backends are
        exhaustive is worth nothing on a run where one of them refused us, because the
        resources in that one would then be reported as unmanaged on the strength of a failure.
        """
        return not self.refused


def management_of(
    provider_id: str,
    *,
    managed: frozenset[str],
    account_id: str,
    exhaustive_accounts: frozenset[str],
    read_was_whole: bool,
) -> ManagementState:
    """The three valued answer for one resource.

    `MANAGED` needs evidence, which is presence in what we read. `UNMANAGED` needs two things
    that are both about our own configuration rather than about the resource: a declaration
    that the account's infrastructure as code is wholly described by the backends we read, and
    a run in which all of them were actually read. Everything else is `NOT_DETERMINED`.

    Pure, and deliberately takes the declaration as an argument rather than reading settings,
    so the rule can be tested against every combination rather than against one deployment.
    """
    if provider_id in managed:
        return ManagementState.MANAGED
    if account_id in exhaustive_accounts and read_was_whole:
        return ManagementState.UNMANAGED
    # The default, and the only safe answer. Absence from an incomplete read is absence of
    # evidence, and absence from a read whose completeness nobody declared is the same.
    return ManagementState.NOT_DETERMINED
