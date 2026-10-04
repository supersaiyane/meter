"""Two Bedrock actions, on named models, in the hub only. Read from the Terraform.

TASK-P7-004 and ADR-0028. The task role may invoke the models it names and nothing else,
never through a wildcard, and no role in a member account gains anything for the
assistant. Read as text, the way `tests/scripts/test_observability.py` reads the hub,
because a plan needs credentials and this needs to run on a laptop inside `make verify`.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TERRAFORM = ROOT / "infra" / "terraform"
HUB = TERRAFORM / "hub"

INVOKE = ("bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream")


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


def _invoke_statement() -> str:
    iam = (HUB / "iam.tf").read_text(encoding="utf-8")
    return _enclosing_block(iam, '"InvokeTheNamedModels"', 'dynamic "statement"')


def test_the_task_role_may_invoke_and_do_nothing_else_with_a_model() -> None:
    statement = _invoke_statement()
    assert tuple(re.findall(r'"(bedrock:[A-Za-z]+)"', statement)) == INVOKE


def test_the_models_are_named_never_a_wildcard() -> None:
    statement = _invoke_statement()
    resources = statement[statement.index("resources") :]
    assert "foundation-model/${model_id}" in resources
    assert "for model_id in statement.value" in resources
    assert "*" not in resources, "a wildcard grants every model the service ever adds"


def test_with_no_model_named_the_role_grants_nothing() -> None:
    """OPEN-10 unanswered is a role without the statement, not one with an empty list."""
    assert "length(var.assistant_model_ids) == 0 ? []" in _invoke_statement()
    variables = (HUB / "variables.tf").read_text(encoding="utf-8")
    declared = _enclosing_block(variables, '"assistant_model_ids"', "variable")
    assert re.search(r"default\s*=\s*\[\]", declared)


def test_the_variable_refuses_a_wildcard_before_a_plan_does() -> None:
    variables = (HUB / "variables.tf").read_text(encoding="utf-8")
    declared = _enclosing_block(variables, '"assistant_model_ids"', "variable")
    assert '!strcontains(model_id, "*")' in declared


def test_nothing_else_in_the_hub_grants_a_bedrock_action() -> None:
    granted = [
        (path.name, action)
        for path, source in _sources(HUB).items()
        for action in re.findall(r'"(bedrock:[A-Za-z*]+)"', source)
    ]
    assert granted == [("iam.tf", action) for action in INVOKE]


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
