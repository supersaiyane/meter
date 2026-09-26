"""Reading Terraform state from the locations an operator configured.

FEAT-057, TASK-P4-013.

**Unproved against a real backend, like every other adapter in this package.** The state format
below is read from the Terraform documentation for state version 4 and from nothing else, and
the tests answer from a literal. ISS-209 records it, on the same footing as ISS-200 and ISS-202.
The part most likely to be wrong is the address: Terraform's own addressing rules for counted
and for_each resources are the piece that is easy to get subtly wrong, and an address that is
slightly wrong points FEAT-040 at the wrong block, which is worse than pointing at none.

**The locations are configured, never discovered.** Listing an account's buckets to see which
hold state is reconnaissance whatever the intent, so this reads what it was given. A location
that cannot be read is reported with its typed cause rather than skipped, because a backend
nobody can read is a configuration gap somebody can fix and a silence is not.

**Nothing is locked.** A Terraform state lock blocks whoever is mid apply, so a tool that took
one could stall somebody's deployment. This reads the object and never takes a lease, which is
constraint 6 in the sense the person on call cares about.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from botocore.exceptions import BotoCoreError, ClientError

from finops_core.domain.iac import ManagedResource, StateRead
from finops_core.errors import CollectionError, Unreachable
from finops_providers.aws.client import translate

COLLECTOR = "iac_state"

#: Only `managed` resources. A state file also records `data` sources, which are reads of
#: things Terraform does not own, and reporting one as managed would tell somebody the resource
#: is in their code when what is in their code is a lookup of it.
MANAGED_MODE = "managed"

#: Where a resource's identifier lives in its attributes. `arn` first because that is what
#: `topology_node` keys on everywhere else. A resource with neither is one we read and cannot
#: place, which the caller counts rather than discards.
IDENTIFIER_KEYS = ("arn",)


def _system_clock() -> datetime:
    return datetime.now(UTC)


def address_of(resource: Any, index: Any = None) -> str:
    """The Terraform address of one resource instance.

    `module.network.aws_vpc.main`, or `aws_vpc.main` at the root, with the index key appended
    for a counted or keyed resource. FEAT-040 opens a pull request against a block, and a bare
    resource name appears in every module that declares one, so the module path is not optional.

    The index is rendered the way Terraform renders it: bare for a count, quoted for a
    for_each key, because `aws_vpc.main[0]` and `aws_vpc.main["a"]` are different addresses and
    a tool that wrote the wrong one would name a block that does not exist.
    """
    module = str(resource.get("module") or "")
    kind = str(resource.get("type") or "")
    name = str(resource.get("name") or "")
    base = ".".join(part for part in (module, kind, name) if part)
    if index is None:
        return base
    if isinstance(index, bool) or not isinstance(index, int):
        return f'{base}["{index}"]'
    return f"{base}[{index}]"


class S3TerraformState:
    """Terraform state read from S3 objects an operator named."""

    def __init__(
        self,
        *,
        client: Any,
        locations: tuple[str, ...],
        clock: Any = _system_clock,
    ) -> None:
        self._client = client
        self._locations = locations
        self._clock = clock

    @property
    def locations(self) -> tuple[str, ...]:
        return self._locations

    def read(self, locations: Iterable[str]) -> StateRead:
        """Every resource the given locations own, and the ones that refused.

        Each location is guarded on its own, so one unreadable backend costs that backend's
        resources rather than the whole read. Raises only where nothing at all could be read,
        because a run that wrote nothing while reporting success is the failure P4 exists to
        prevent, and an estate whose every backend refused us is not a partial answer.
        """
        wanted = tuple(locations)
        found: list[ManagedResource] = []
        refused: list[tuple[str, str]] = []
        at = self._clock()

        for location in wanted:
            try:
                found.extend(self._one(location, at))
            except (ClientError, BotoCoreError) as failure:
                typed = translate(failure, scope_key=location, collector=COLLECTOR)
                refused.append((location, type(typed).__name__))
            except CollectionError as failure:
                refused.append((location, type(failure).__name__))
            except json.JSONDecodeError:
                # Not a crash and not silence. An object at a state location that is not JSON is
                # a configuration mistake, usually a path pointing at a directory marker or at a
                # lock file, and naming it as schema drift sends somebody to look at the path.
                refused.append((location, "SchemaDrift"))

        if wanted and len(refused) == len(wanted):
            raise Unreachable(
                scope_key=",".join(wanted),
                collector=COLLECTOR,
                detail=f"none of the {len(wanted)} configured state locations could be read",
            )
        return StateRead(managed=tuple(found), refused=tuple(refused))

    def _one(self, location: str, at: datetime) -> list[ManagedResource]:
        parsed = urlsplit(location)
        if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
            # Refused rather than attempted. A location this adapter cannot parse would
            # otherwise become a confusing error from the SDK about an empty key.
            raise Unreachable(
                scope_key=location,
                collector=COLLECTOR,
                detail=f"{location} is not an s3 URL of the form s3://bucket/key",
            )
        response = self._client.get_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))
        document = json.loads(response["Body"].read())

        found: list[ManagedResource] = []
        for resource in document.get("resources") or ():
            if resource.get("mode") != MANAGED_MODE:
                continue
            for instance in resource.get("instances") or ():
                attributes = instance.get("attributes") or {}
                identifier = next(
                    (str(attributes[key]) for key in IDENTIFIER_KEYS if attributes.get(key)),
                    None,
                )
                if identifier is None:
                    # Read and unplaceable. Counted by the collector rather than dropped here,
                    # because a state file full of resources we cannot join is a fact about our
                    # own matching and the collector is where that is reported.
                    continue
                found.append(
                    ManagedResource(
                        provider_id=identifier,
                        address=address_of(resource, instance.get("index_key")),
                        state_reference=location,
                        as_of=at,
                        collected_at=at,
                    )
                )
        return found
