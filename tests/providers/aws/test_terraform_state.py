"""The state adapter, against literals.

FEAT-057, TASK-P4-013. Unproved against a real backend, ISS-209, on the same footing as
ISS-200 and ISS-202. Every response here is read from the Terraform documentation for state
version 4 and from nothing else.

The addressing cases carry this file. An address that is slightly wrong points FEAT-040 at the
wrong block, which is worse than pointing at none, and Terraform's rules for counted and keyed
resources are the part that is easy to get subtly wrong: `aws_vpc.main[0]` and
`aws_vpc.main["a"]` are different addresses and only one of them exists in any given file.
"""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
from botocore.exceptions import ClientError

from finops_core.errors import Unreachable
from finops_providers.aws.terraform_state import S3TerraformState, address_of

NETWORK = "s3://example-state/network.tfstate"
OTHER = "s3://example-state/app.tfstate"

VPC_ARN = "arn:aws:ec2:eu-west-1:111122223333:vpc/vpc-main"


def document(*resources: dict[str, Any]) -> dict[str, Any]:
    return {"version": 4, "terraform_version": "1.9.5", "resources": list(resources)}


def resource(
    *,
    module: str | None = "module.network",
    kind: str = "aws_vpc",
    name: str = "main",
    mode: str = "managed",
    instances: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"mode": mode, "type": kind, "name": name}
    if module is not None:
        body["module"] = module
    body["instances"] = instances if instances is not None else [{"attributes": {"arn": VPC_ARN}}]
    return body


class FakeS3:
    """One object per location, or a refusal."""

    def __init__(self, objects: dict[str, Any], *, refuse: set[str] | None = None) -> None:
        self._objects = objects
        self._refuse = refuse or set()

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803
        location = f"s3://{Bucket}/{Key}"
        if location in self._refuse:
            raise ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "GetObject")
        body = self._objects[location]
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        return {"Body": io.BytesIO(raw)}


def source(objects: dict[str, Any], *, refuse: set[str] | None = None) -> S3TerraformState:
    return S3TerraformState(client=FakeS3(objects, refuse=refuse), locations=tuple(objects))


# --- the address, which is the part that has to be exactly right -------------


def test_a_module_resource_carries_its_module_path() -> None:
    """A bare resource name appears in every module that declares one, so an address without
    the module path names no file and FEAT-040 could not open a pull request against it."""
    assert address_of(resource()) == "module.network.aws_vpc.main"


def test_a_root_resource_has_no_module_prefix() -> None:
    assert address_of(resource(module=None)) == "aws_vpc.main"


def test_a_counted_resource_uses_a_bare_index() -> None:
    assert address_of(resource(), 0) == "module.network.aws_vpc.main[0]"


def test_a_keyed_resource_uses_a_quoted_key() -> None:
    """The distinction that matters. `aws_vpc.main[0]` and `aws_vpc.main["a"]` are different
    addresses, and a tool writing the wrong one names a block that does not exist."""
    assert address_of(resource(), "a") == 'module.network.aws_vpc.main["a"]'


def test_a_boolean_key_is_quoted_rather_than_treated_as_an_index() -> None:
    """A bool is an int in Python, so a naive integer check renders `true` as `[1]`. Terraform
    for_each keys are strings, and this is the case that catches the shortcut."""
    assert address_of(resource(), True) == 'module.network.aws_vpc.main["True"]'


# --- what a read returns ----------------------------------------------------


def test_a_managed_resource_with_an_arn_is_returned() -> None:
    found = source({NETWORK: document(resource())}).read([NETWORK])
    assert len(found.managed) == 1
    assert found.managed[0].provider_id == VPC_ARN
    assert found.managed[0].state_reference == NETWORK
    assert found.is_whole


def test_a_data_source_is_not_reported_as_managed() -> None:
    """A state file records reads of things Terraform does not own. Reporting one as managed
    would tell somebody the resource is in their code when what is in their code is a lookup."""
    found = source({NETWORK: document(resource(mode="data"))}).read([NETWORK])
    assert found.managed == ()


def test_a_resource_with_no_arn_is_skipped_rather_than_guessed_at() -> None:
    """An association or an attachment has no ARN at all and cannot be joined to anything Meter
    inventoried. Skipped here and counted by the collector, because inventing an identifier
    would produce a row pointing at nothing."""
    found = source(
        {NETWORK: document(resource(instances=[{"attributes": {"id": "rtbassoc-1"}}]))}
    ).read([NETWORK])
    assert found.managed == ()


def test_each_instance_of_a_counted_resource_is_its_own_row() -> None:
    found = source(
        {
            NETWORK: document(
                resource(
                    instances=[
                        {"index_key": 0, "attributes": {"arn": f"{VPC_ARN}-0"}},
                        {"index_key": 1, "attributes": {"arn": f"{VPC_ARN}-1"}},
                    ]
                )
            )
        }
    ).read([NETWORK])
    assert {one.address for one in found.managed} == {
        "module.network.aws_vpc.main[0]",
        "module.network.aws_vpc.main[1]",
    }


# --- the refusals -----------------------------------------------------------


def test_one_unreadable_location_costs_that_location_and_not_the_read() -> None:
    """A read that discarded its results on one failure would make a single unreachable backend
    look like an estate with no infrastructure as code at all."""
    found = source({NETWORK: document(resource()), OTHER: document()}, refuse={OTHER}).read(
        [NETWORK, OTHER]
    )
    assert len(found.managed) == 1
    assert found.refused == ((OTHER, "AccessDenied"),)
    assert not found.is_whole


def test_every_location_refusing_raises_rather_than_returning_empty() -> None:
    """A configuration failure rather than a partial answer. A run that wrote nothing while
    reporting success is the failure this sub project exists to prevent, and an estate whose
    every backend refused us is not an estate with no code."""
    with pytest.raises(Unreachable):
        source({NETWORK: document()}, refuse={NETWORK}).read([NETWORK])


def test_an_object_that_is_not_json_is_schema_drift_rather_than_a_crash() -> None:
    """Usually a path pointing at a directory marker or a lock file. Naming it sends somebody to
    look at the path, and a traceback about JSON does not."""
    found = source({NETWORK: b"not json", OTHER: document(resource())}).read([NETWORK, OTHER])
    assert found.refused == ((NETWORK, "SchemaDrift"),)
    assert len(found.managed) == 1


@pytest.mark.parametrize("bad", ["https://example.com/state", "s3://bucket-only", "s3:///key"])
def test_a_location_that_is_not_an_s3_url_is_refused_by_name(bad: str) -> None:
    """Refused rather than attempted, so the message names the configuration rather than arriving
    from the SDK as a complaint about an empty key. A second, valid location keeps the read
    alive, which is what makes this a refusal of one location and not of the run."""
    found = source({NETWORK: document(resource())}).read([bad, NETWORK])
    assert found.refused == ((bad, "Unreachable"),)
    assert len(found.managed) == 1


def test_a_read_of_only_an_unparseable_location_raises() -> None:
    """Nothing was read at all, which is a configuration failure rather than a partial answer."""
    with pytest.raises(Unreachable):
        source({NETWORK: document()}).read(["s3://bucket-only"])
