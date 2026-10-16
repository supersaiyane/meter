"""A plan reduced to what sets its price. TASK-P16-002, FEAT-095, spec section 5.2.

Plans as `terraform show -json` writes them for Terraform 1.x. What is kept is the address, type,
actions, Region and priced attributes of each AWS resource change; a value planted in every field
the reduction drops, the sensitive ones included, is found nowhere in what it returns.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from finops_query.plan_reading import (
    MAX_PLAN_BYTES,
    PlannedChange,
    ReducedPlan,
    Unreadable,
    reduce_plan,
)

AWS = "registry.terraform.io/hashicorp/aws"
SECRET = "planted-c0ffee-value"


def change(
    address: str,
    resource_type: str,
    after: dict[str, Any] | None,
    *,
    actions: tuple[str, ...] = ("create",),
    before: dict[str, Any] | None = None,
    module: str | None = None,
    mode: str = "managed",
    provider: str = AWS,
    **marks: Any,
) -> dict[str, Any]:
    """One entry of `resource_changes`; `marks` are `after_unknown` and the sensitivities."""
    entry: dict[str, Any] = {
        "address": address,
        "mode": mode,
        "type": resource_type,
        "name": address.split(".")[-1].split("[")[0],
        "provider_name": provider,
        "change": {"actions": list(actions), "before": before, "after": after, **marks},
    }
    if module is not None:
        entry["module_address"] = module
    return entry


def constant(region: str) -> dict[str, Any]:
    return {"name": "aws", "expressions": {"region": {"constant_value": region}}}


def plan(*changes: dict[str, Any], **top: Any) -> bytes:
    document: dict[str, Any] = {
        "format_version": "1.2",
        "terraform_version": "1.9.8",
        "planned_values": {"root_module": {}},
        "resource_changes": list(changes),
        "configuration": {
            "provider_config": top.pop("providers", {"aws": constant("eu-west-1")}),
            "root_module": top.pop("root_module", {}),
        },
    }
    document.update(top)
    return json.dumps(document).encode()


def reduced(document: bytes) -> ReducedPlan:
    found = reduce_plan(document)
    assert isinstance(found, ReducedPlan), found
    return found


def only(document: bytes) -> PlannedChange:
    (one,) = reduced(document).changes
    return one


def test_a_created_instance_keeps_its_priced_attributes_and_nothing_else() -> None:
    entry = change(
        "aws_instance.web",
        "aws_instance",
        {
            "ami": "ami-0abc",
            "instance_type": "m6i.large",
            "tenancy": "default",
            "user_data": SECRET,
            "tags": {"Owner": SECRET},
            "root_block_device": [
                {
                    "volume_type": "gp3",
                    "volume_size": 50,
                    "iops": 3000,
                    "throughput": 125,
                    "kms_key_id": SECRET,
                    "tags": {"Name": SECRET},
                },
            ],
        },
        after_unknown={"arn": True, "availability_zone": True, "id": True},
    )
    assert only(plan(entry)) == PlannedChange(
        address="aws_instance.web",
        resource_type="aws_instance",
        actions=("create",),
        region="eu-west-1",
        before={},
        after={
            "instance_type": "m6i.large",
            "tenancy": "default",
            "root_block_device": [
                {"volume_type": "gp3", "volume_size": 50, "iops": 3000, "throughput": 125}
            ],
        },
    )


def test_a_value_planted_in_every_field_the_reduction_drops_is_found_nowhere() -> None:
    database = change(
        "aws_db_instance.main",
        "aws_db_instance",
        {
            "instance_class": "db.m6g.large",
            "engine": "postgres",
            "password": SECRET,
            "username": SECRET,
            "allocated_storage": 100,
        },
        actions=("update",),
        before={
            "instance_class": "db.m6g.xlarge",
            "engine": "postgres",
            "password": SECRET,
            "allocated_storage": 100,
        },
        after_sensitive={"password": True},
        before_sensitive={"password": True},
    )
    document = plan(
        database,
        change(
            "aws_instance.app",
            "aws_instance",
            {"instance_type": SECRET, "user_data": SECRET},
            after_sensitive={"instance_type": True, "user_data": True},
        ),
        change("aws_iam_policy.reader", "aws_iam_policy", {"policy": SECRET, "name": SECRET}),
        change("data.aws_ami.base", "aws_ami", {"id": SECRET}, mode="data", actions=("read",)),
        change(
            "random_password.db",
            "random_password",
            {"result": SECRET},
            provider="registry.terraform.io/hashicorp/random",
        ),
        variables={"region": {"value": "eu-west-1"}, "db_password": {"value": SECRET}},
        prior_state={"values": {"root_module": {"resources": [{"values": {"password": SECRET}}]}}},
        planned_values={"root_module": {"resources": [{"values": {"password": SECRET}}]}},
        output_changes={"connection": {"change": {"after": SECRET}}},
        resource_drift=[{"change": {"after": {"password": SECRET}}}],
        relevant_attributes=[{"resource": SECRET, "attribute": ["password"]}],
        root_module={
            "resources": [
                {
                    "address": "aws_db_instance.main",
                    "mode": "managed",
                    "type": "aws_db_instance",
                    "name": "main",
                    "provider_config_key": "aws",
                    "expressions": {"password": {"constant_value": SECRET}},
                }
            ]
        },
    )
    found = reduced(document)
    assert SECRET not in repr(found)
    by_address = {one.address: one for one in found.changes}
    assert set(by_address) == {"aws_db_instance.main", "aws_instance.app", "aws_iam_policy.reader"}
    assert by_address["aws_instance.app"].withheld == ("instance_type",)
    assert by_address["aws_iam_policy.reader"].after == {}
    assert by_address["aws_db_instance.main"].before["instance_class"] == "db.m6g.xlarge"


def test_module_instances_find_their_provider_configuration_and_its_region() -> None:
    providers = {"aws": constant("eu-west-1"), "aws.west": constant("us-west-2")}
    web = {
        "mode": "managed",
        "type": "aws_instance",
        "name": "web",
        "provider_config_key": "aws.west",
    }
    data = {
        "mode": "managed",
        "type": "aws_ebs_volume",
        "name": "data",
        "provider_config_key": "aws",
    }
    root_module = {"resources": [data], "module_calls": {"app": {"module": {"resources": [web]}}}}
    document = plan(
        change(
            'module.app["a"].aws_instance.web',
            "aws_instance",
            {"instance_type": "t3.micro"},
            module='module.app["a"]',
        ),
        change("aws_ebs_volume.data[0]", "aws_ebs_volume", {"type": "gp3", "size": 20}),
        providers=providers,
        root_module=root_module,
    )
    regions = {one.address: one.region for one in reduced(document).changes}
    assert regions == {
        'module.app["a"].aws_instance.web': "us-west-2",
        "aws_ebs_volume.data[0]": "eu-west-1",
    }


def test_a_root_variable_gives_the_region_and_a_module_providers_variable_does_not() -> None:
    by_variable = {"name": "aws", "expressions": {"region": {"references": ["var.region"]}}}
    root = {
        "mode": "managed",
        "type": "aws_ebs_volume",
        "name": "root",
        "provider_config_key": "aws",
    }
    inner = {
        "mode": "managed",
        "type": "aws_ebs_volume",
        "name": "inner",
        "provider_config_key": "disks:aws",
    }
    document = plan(
        change("aws_ebs_volume.root", "aws_ebs_volume", {"type": "gp3", "size": 8}),
        change(
            "module.disks.aws_ebs_volume.inner",
            "aws_ebs_volume",
            {"type": "gp3", "size": 8},
            module="module.disks",
        ),
        providers={"aws": by_variable, "disks:aws": by_variable},
        root_module={
            "resources": [root],
            "module_calls": {"disks": {"module": {"resources": [inner]}}},
        },
        variables={"region": {"value": "ap-south-1"}},
    )
    regions = {one.address: one.region for one in reduced(document).changes}
    assert regions == {
        "aws_ebs_volume.root": "ap-south-1",
        "module.disks.aws_ebs_volume.inner": None,
    }


@pytest.mark.parametrize(
    ("after", "region"),
    [
        ({"region": "eu-central-1", "availability_zone": "eu-west-1a"}, "eu-central-1"),
        ({"availability_zone": "eu-west-2b"}, "eu-west-2"),
        ({"availability_zone": "us-west-2-lax-1a"}, "us-east-1"),
        ({"region": "not-a-region"}, "us-east-1"),
    ],
)
def test_the_resources_own_region_comes_first_then_its_zone_then_the_provider(
    after: dict[str, Any], region: str
) -> None:
    entry = change("aws_ebs_volume.data", "aws_ebs_volume", {"type": "gp3", "size": 8, **after})
    assert only(plan(entry, providers={"aws": constant("us-east-1")})).region == region


@pytest.mark.parametrize(
    "providers",
    [
        {"aws": {"name": "aws", "expressions": {}}},
        {"aws": {"name": "aws", "expressions": {"region": {"references": ["local.region"]}}}},
        {"aws": {"name": "aws", "expressions": {"region": {"references": ["var.missing"]}}}},
        {"aws": constant("eu-west-1"), "aws.west": constant("us-west-2")},
        {"aws": constant("mars-north")},
        {},
    ],
)
def test_with_no_region_it_can_read_for_certain_the_region_is_none(
    providers: dict[str, Any],
) -> None:
    entry = change("aws_ebs_volume.data", "aws_ebs_volume", {"type": "gp3", "size": 8})
    assert only(plan(entry, providers=providers)).region is None


def test_values_known_only_after_apply_are_named() -> None:
    entry = change(
        "aws_instance.web",
        "aws_instance",
        {"tenancy": "default", "root_block_device": [{"volume_type": "gp3"}]},
        after_unknown={
            "instance_type": True,
            "root_block_device": [{"volume_size": True, "volume_id": True}],
            "ebs_block_device": True,
        },
    )
    assert only(plan(entry)).unknown == (
        "instance_type",
        "root_block_device[0].volume_size",
        "ebs_block_device",
    )


def test_a_priced_attribute_marked_sensitive_is_named_and_not_kept() -> None:
    entry = change(
        "aws_instance.web",
        "aws_instance",
        {"instance_type": SECRET, "root_block_device": [{"volume_type": "gp3", "volume_size": 9}]},
        after_sensitive={"instance_type": True, "root_block_device": [{"volume_size": True}]},
    )
    found = only(plan(entry))
    assert found.withheld == ("instance_type", "root_block_device[0].volume_size")
    assert found.after == {"root_block_device": [{"volume_type": "gp3"}]}


def test_a_destroy_keeps_its_before_and_a_replacement_keeps_both_sides() -> None:
    gp2 = {"type": "gp2", "size": 100, "availability_zone": "eu-west-2a", "tags": {"x": SECRET}}
    gone = change("aws_ebs_volume.old", "aws_ebs_volume", None, actions=("delete",), before=gp2)
    destroyed = only(plan(gone))
    assert (destroyed.before, destroyed.after) == ({"type": "gp2", "size": 100}, {})
    assert (destroyed.region, destroyed.unknown) == ("eu-west-2", ())
    swapped = change(
        "aws_ebs_volume.old",
        "aws_ebs_volume",
        {"type": "gp3", "size": 100},
        actions=("delete", "create"),
        before=gp2,
    )
    replaced = only(plan(swapped))
    assert replaced.actions == ("delete", "create")
    assert (replaced.before["type"], replaced.after["type"]) == ("gp2", "gp3")


def test_changes_that_bill_nothing_and_other_providers_are_dropped() -> None:
    document = plan(
        change(
            "aws_instance.same", "aws_instance", {"instance_type": "t3.micro"}, actions=("no-op",)
        ),
        change("aws_instance.gone", "aws_instance", None, actions=("forget",)),
        change(
            "data.aws_region.here",
            "aws_region",
            {"name": "eu-west-1"},
            mode="data",
            actions=("read",),
        ),
        change(
            "google_compute_instance.vm",
            "google_compute_instance",
            {"machine_type": "e2-small"},
            provider="registry.terraform.io/hashicorp/google",
        ),
    )
    assert reduced(document).changes == ()


def test_an_unpriced_type_keeps_only_what_names_it_and_opentofu_is_read_alike() -> None:
    entry = change(
        "aws_nat_gateway.out",
        "aws_nat_gateway",
        {"allocation_id": "eipalloc-1"},
        provider="registry.opentofu.org/hashicorp/aws",
    )
    found = only(plan(entry))
    assert (found.resource_type, found.region, found.before, found.after) == (
        "aws_nat_gateway",
        "eu-west-1",
        {},
        {},
    )


def test_search_domain_blocks_keep_only_their_priced_parts_in_either_shape() -> None:
    entry = change(
        "aws_opensearch_domain.logs",
        "aws_opensearch_domain",
        {
            "cluster_config": [
                {
                    "instance_type": "r6g.large.search",
                    "instance_count": 3,
                    "zone_awareness_enabled": True,
                }
            ],
            "ebs_options": {"ebs_enabled": True, "volume_size": 100, "volume_type": "gp3"},
            "access_policies": SECRET,
        },
    )
    assert only(plan(entry)).after == {
        "cluster_config": [{"instance_type": "r6g.large.search", "instance_count": 3}],
        "ebs_options": [{"ebs_enabled": True, "volume_size": 100, "volume_type": "gp3"}],
    }


def test_the_versions_and_the_plans_own_timestamp_are_kept() -> None:
    found = reduced(plan(timestamp="2026-10-16T09:00:00Z"))
    assert (found.format_version, found.terraform_version) == ("1.2", "1.9.8")
    assert found.timestamp == datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
    assert found.changes == ()
    assert reduced(plan(timestamp="yesterday")).timestamp is None
    assert reduced(plan(terraform_version=None)).terraform_version is None


def refused(document: bytes) -> str:
    found = reduce_plan(document)
    assert isinstance(found, Unreadable), found
    return found.reason


def entries(*changes: Any) -> bytes:
    return json.dumps({"format_version": "1.2", "resource_changes": list(changes)}).encode()


NAMED = {"address": "a.b", "mode": "managed", "type": "a", "name": "b"}


@pytest.mark.parametrize(
    ("document", "says"),
    [
        (b"not json", "not JSON: Expecting value at line 1"),
        (b"\xff\xfe\xfd", "not JSON Meter can read"),
        (b"[" * 100_000 + b"]" * 100_000, "not JSON Meter can read: RecursionError"),
        (b"[]", "not a JSON object"),
        (b'{"terraform_version": "1.9.8"}', "no format_version"),
        (b'{"format_version": "2.0", "planned_values": {}}', "is 2.0; Meter reads 1.x"),
        (b'{"format_version": "1.0", "values": {}}', "it is not a plan"),
        (b'{"format_version": "1.2", "resource_changes": {"a": 1}}', "is not a list"),
        (entries(7), "resource change 0 is not as Terraform writes one: not an object"),
        (entries({"mode": "managed"}), "no address"),
        (entries(NAMED), "no change"),
        (entries({**NAMED, "change": {"actions": "create"}}), "no actions"),
    ],
)
def test_what_is_not_a_plan_meter_reads_is_refused_with_the_reason(
    document: bytes, says: str
) -> None:
    assert says in refused(document)


def test_a_plan_over_the_limit_is_refused_before_it_is_read() -> None:
    assert refused(b" " * (MAX_PLAN_BYTES + 1)) == (
        "the plan is 50.0 MiB; Meter reads a plan up to 50 MiB"
    )
