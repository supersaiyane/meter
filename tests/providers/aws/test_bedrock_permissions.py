"""Two Bedrock actions, through tagged profiles of named models, in the hub only. Read from
the Terraform.

TASK-P7-004, ADR-0028 and ISS-230. The task role may invoke the models it names and nothing
else, never through a wildcard, and no role in a member account gains anything for the
assistant. It reaches each model only through an application inference profile tagged
`finops:module`, because an on demand call is not a resource, no tag reaches its cost line,
and the platform cost screen could not say what the assistant costs. Read as text, the way
`tests/scripts/test_observability.py` reads the hub, because a plan needs credentials and
this needs to run on a laptop inside `make verify`.
"""

from __future__ import annotations

import re
from pathlib import Path

from finops_core.config import Settings
from finops_core.constants import ENV_PREFIX, PLATFORM_TAG_KEY
from finops_core.domain.platform import UNALLOCATED

ROOT = Path(__file__).resolve().parents[3]
TERRAFORM = ROOT / "infra" / "terraform"
HUB = TERRAFORM / "hub"

INVOKE = ("bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream")
THROUGH_THE_PROFILE = "bedrock:InferenceProfileArn"

#: The statement naming the profiles, and the one naming the models behind them.
PROFILES = "InvokeThroughTheTaggedProfiles"
MODELS = "ReachTheModelsOnlyThroughTheProfiles"

#: The module the assistant's spend is reported under on the platform cost screen.
ASSISTANT_MODULE = "assistant"
PROFILE_ARN = "aws_bedrock_inference_profile.assistant[model_id].arn"


def _sources(stack: Path) -> dict[Path, str]:
    """Every Terraform file in a stack, skipping the provider cache."""
    return {
        path: path.read_text(encoding="utf-8")
        for path in sorted(stack.rglob("*.tf"))
        if ".terraform" not in path.parts
    }


def _enclosing_block(source: str, marker: str, opener: str) -> str:
    """The brace balanced block that opens at the last `opener` before `marker`."""
    start = source.rindex(opener, 0, source.index(marker))
    depth = 0
    for index in range(source.index("{", start), len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"the block holding {marker} never closes")


def _hub(name: str) -> str:
    return (HUB / name).read_text(encoding="utf-8")


def _statement(sid: str) -> str:
    return _enclosing_block(_hub("iam.tf"), f'"{sid}"', 'dynamic "statement"')


def _profile() -> str:
    return _enclosing_block(
        _hub("iam.tf"), '"aws_bedrock_inference_profile" "assistant"', "resource"
    )


def _variable(name: str) -> str:
    return _enclosing_block(_hub("variables.tf"), f'"{name}"', "variable")


# --- the grant -------------------------------------------------------------------------


def test_the_task_role_may_invoke_and_do_nothing_else_with_a_model() -> None:
    for sid in (PROFILES, MODELS):
        statement = _statement(sid)
        actions = statement[statement.index("actions") : statement.index("resources")]
        assert tuple(re.findall(r'"(bedrock:[A-Za-z]+)"', actions)) == INVOKE, sid


def test_the_role_invokes_the_profiles_it_names() -> None:
    """The ARN of a profile this stack creates, never one assembled from a string."""
    statement = _statement(PROFILES)
    resources = statement[statement.index("resources") :]
    assert f"for model_id in statement.value : {PROFILE_ARN}" in resources
    assert "condition" not in statement


def test_the_models_are_named_never_a_wildcard() -> None:
    for sid in (PROFILES, MODELS):
        statement = _statement(sid)
        resources = statement[statement.index("resources") :]
        assert "for model_id in statement.value" in resources, sid
        assert "*" not in resources, "a wildcard grants every model the service ever adds"
    models = _statement(MODELS)
    assert "foundation-model/${model_id}" in models[models.index("resources") :]


def test_a_model_is_reached_only_through_its_profile() -> None:
    """ISS-230. Named directly, a model answers untagged, so the grant forbids that call."""
    statement = _statement(MODELS)
    condition = _enclosing_block(statement, f'"{THROUGH_THE_PROFILE}"', "condition")
    assert re.search(r'test\s*=\s*"ArnEquals"', condition)
    assert re.search(rf'variable\s*=\s*"{THROUGH_THE_PROFILE}"', condition)
    assert f"for model_id in statement.value : {PROFILE_ARN}" in condition


def test_with_no_model_named_the_role_grants_nothing() -> None:
    """OPEN-10 unanswered is a role without the statements, not one with an empty list."""
    for sid in (PROFILES, MODELS):
        assert "length(var.assistant_model_ids) == 0 ? []" in _statement(sid), sid
    assert "for_each = toset(var.assistant_model_ids)" in _profile()
    assert re.search(r"default\s*=\s*\[\]", _variable("assistant_model_ids"))


def test_the_variable_refuses_a_wildcard_before_a_plan_does() -> None:
    assert '!strcontains(model_id, "*")' in _variable("assistant_model_ids")


def test_nothing_else_in_the_hub_grants_a_bedrock_action() -> None:
    """The two actions in each of the two statements, and the one condition key."""
    named = [
        (path.name, name)
        for path, source in _sources(HUB).items()
        for name in re.findall(r'"(bedrock:[A-Za-z*]+)"', source)
    ]
    assert named == [("iam.tf", name) for name in (*INVOKE, *INVOKE, THROUGH_THE_PROFILE)]


def test_no_member_or_management_role_gains_anything() -> None:
    """The model runs in the hub. A member account role that could invoke one would be a
    second place the assistant could run, with nobody's cost screen watching it."""
    elsewhere = [
        str(path.relative_to(ROOT))
        for stack in sorted(p for p in TERRAFORM.iterdir() if p.is_dir() and p.name != "hub")
        for path, source in _sources(stack).items()
        if "bedrock" in source.lower()
    ]
    assert elsewhere == []


# --- the profile and its tag -----------------------------------------------------------


def test_each_profile_copies_its_named_model_in_this_region() -> None:
    copy_from = re.search(r'copy_from\s*=\s*"([^"]+)"', _profile())
    assert copy_from is not None
    assert copy_from.group(1) == (
        "arn:${data.aws_partition.current.partition}:bedrock:${var.region}"
        "::foundation-model/${each.value}"
    )


def test_each_profile_carries_the_tag_the_platform_cost_collector_groups_by() -> None:
    """Constraint 7. The key is the collector's own constant, so the two cannot drift."""
    tags = _enclosing_block(_profile(), f'"{PLATFORM_TAG_KEY}"', "tags")
    assert re.search(rf'"{PLATFORM_TAG_KEY}"\s*=\s*"{ASSISTANT_MODULE}"', tags)


def test_the_assistant_is_a_module_of_its_own() -> None:
    """Folded into the stack default, the screen could not say what the assistant costs."""
    default = re.search(rf'"{PLATFORM_TAG_KEY}"\s*=\s*"([^"]+)"', _hub("versions.tf"))
    assert default is not None
    assert ASSISTANT_MODULE not in (default.group(1), UNALLOCATED)


# --- what the API is told --------------------------------------------------------------


def test_the_api_records_the_model_and_calls_through_the_profile() -> None:
    """Only the API builds the model. It is told the model's identifier, which an exchange
    records, and the profile's ARN, which it calls, because only that call is tagged and
    the ARN names an account a screen has no reason to show.

    Since TASK-P12-006 every setting is an SSM parameter and every Python task is given every
    one, because each loads the whole settings model; the worker and the dispatcher share the
    API's task role, so withholding the two values from them was never a boundary. What keeps
    the model the API's is that nothing else builds one, which the last assertion holds."""
    settings = _hub("settings.tf")
    model = f"{ENV_PREFIX}ASSISTANT_MODEL_ID"
    profile = f"{ENV_PREFIX}ASSISTANT_INFERENCE_PROFILE_ARN"
    assert {"assistant_model_id", "assistant_inference_profile_arn"} <= set(Settings.model_fields)
    assert re.search(rf"{model}\s+=\s+var\.assistant_model_in_use\n", settings)
    told = re.search(rf"{profile}\s+=\s+(.+)\n", settings)
    assert told and "aws_bedrock_inference_profile.assistant[var.assistant_model_in_use].arn" in (
        told.group(1)
    )
    assert settings.count(model) == 1 and settings.count(profile) == 1
    builders = sorted(
        str(path.relative_to(ROOT))
        for package in ROOT.glob("finops_*")
        for path in package.rglob("*.py")
        if "language_model(" in path.read_text() and path.name != "language_model.py"
    )
    assert builders == ["finops_api/main.py"]


def test_the_model_in_use_is_one_that_was_named() -> None:
    declared = _variable("assistant_model_in_use")
    assert re.search(r'default\s*=\s*""', declared)
    assert "contains(var.assistant_model_ids, var.assistant_model_in_use)" in declared


def test_the_profile_arns_are_an_output() -> None:
    output = _enclosing_block(_hub("outputs.tf"), '"assistant_inference_profile_arns"', "output")
    assert "aws_bedrock_inference_profile.assistant : model_id => profile.arn" in output
