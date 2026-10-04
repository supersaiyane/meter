"""The model port, what its values refuse, and the names it must never use.

TASK-P7-001 and ADR-0028. The protocol names completion, tool schemas and a token
count. It names no vendor, no model identifier and no region, and nothing in the
three packages above the providers names a model or a vendor either. A deployment
that changes model changes a setting, and the scans below are what make that true
rather than intended.

The scans read code, not prose. A docstring may say what a module does not name, and
a scan that tripped on that sentence would teach the next author to stop writing it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from finops_core.ports.llm import (
    Completion,
    CompletionRequest,
    Message,
    Role,
    StopReason,
    TokenUsage,
    ToolCall,
    ToolResult,
    ToolSchema,
)

ROOT = Path(__file__).resolve().parent.parent.parent
PORT = ROOT / "finops_core" / "ports" / "llm.py"

#: Vendor and model family names. A closed list, so adding one is a reviewed diff.
VENDOR = re.compile(r"\b(bedrock|anthropic|claude|openai|titan|llama|mistral|cohere|gemini)\b")

#: What a vendor neutral port has no reason to name.
PROVIDER_DETAIL = re.compile(r"\b(region|model id|modelid|arn)\b")

#: ADR-0028: nothing in these names a model or a vendor.
NEUTRAL_PACKAGES = ("finops_core", "finops_query", "finops_api")

#: The repository's rules file. Error messages cite it by name, and that cites a file
#: rather than naming a model the product uses. Found by the first run of the scan.
RULES_FILE = "CLAUDE.md"


def _words(name: str) -> str:
    """`BedrockModel` and `bedrock_model` both read as `bedrock model`."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name.replace(RULES_FILE, ""))
    return re.sub(r"[^a-z0-9]+", " ", spaced.lower())


def names_in(tree: ast.AST) -> set[str]:
    """Every name code uses: identifiers, attributes, arguments, imports and string
    literals, with docstrings and other bare string statements left out."""
    prose = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    }
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, (ast.arg, ast.keyword)):
            found.update(filter(None, (node.arg,)))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.alias):
            found.update(filter(None, (node.name, node.asname)))
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif (
            isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in prose
        ):
            found.add(node.value)
    return found


def _offences(path: Path, pattern: re.Pattern[str]) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return sorted(
        f"{path.relative_to(ROOT)}: {name!r}"
        for name in names_in(tree)
        if pattern.search(_words(name))
    )


# --- what the port names ---------------------------------------------------------


def test_the_port_names_no_vendor() -> None:
    assert _offences(PORT, VENDOR) == []


def test_the_port_names_no_model_identifier_and_no_region() -> None:
    """Both are the adapter's configuration. A port method taking a region is a port
    that has decided where the model runs, which is ADR-0028's decision, not its."""
    assert _offences(PORT, PROVIDER_DETAIL) == []


def test_nothing_above_the_providers_names_a_model_or_a_vendor() -> None:
    """ADR-0028's consequence, held across the three packages rather than one file.

    Composition still has to name the adapter somewhere, and that somewhere is
    `finops_providers`, which is below this line and is where a vendor belongs.
    """
    offences = [
        offence
        for package in NEUTRAL_PACKAGES
        for path in sorted((ROOT / package).rglob("*.py"))
        for offence in _offences(path, VENDOR)
    ]
    assert offences == []


def test_the_scan_sees_a_vendor_in_code_and_ignores_one_in_prose() -> None:
    """The positive case, so the scans above cannot pass by seeing nothing."""
    code = ast.parse('"""Says Bedrock in prose."""\nfrom x.bedrock import BedrockModel\n')
    assert any(VENDOR.search(_words(name)) for name in names_in(code))
    prose_only = ast.parse('"""Says Bedrock in prose, and nothing else does."""\n')
    assert not any(VENDOR.search(_words(name)) for name in names_in(prose_only))
    citing_the_rules = ast.parse('detail = "See constraint 3 in CLAUDE.md."\n')
    assert not any(VENDOR.search(_words(name)) for name in names_in(citing_the_rules))


# --- the values, and what each refuses -------------------------------------------


def _ask() -> Message:
    return Message(role=Role.USER, text="What did we spend last month?")


def test_a_tool_needs_a_plain_name_a_description_and_object_arguments() -> None:
    with pytest.raises(ValueError, match="lower snake case"):
        ToolSchema(name="Get-Cost", description="Cost by service.")
    with pytest.raises(ValueError, match="chooses by it"):
        ToolSchema(name="get_cost", description="   ")
    with pytest.raises(ValueError, match="one object"):
        ToolSchema(name="get_cost", description="Cost.", parameters={"type": "array"})
    assert ToolSchema(name="get_cost", description="Cost.").parameters["type"] == "object"


def test_a_tool_call_may_name_a_tool_that_does_not_exist() -> None:
    """The loop refuses an unknown tool by name, so the name has to survive to it."""
    call = ToolCall(call_id="t1", name="Forecast Next Month")
    assert call.name == "Forecast Next Month"
    with pytest.raises(ValueError, match="paired"):
        ToolCall(call_id=" ", name="get_cost")


def test_only_the_assistant_asks_for_tools_and_only_the_user_returns_results() -> None:
    with pytest.raises(ValueError, match="only the assistant"):
        Message(role=Role.USER, tool_calls=(ToolCall(call_id="t1", name="get_cost"),))
    with pytest.raises(ValueError, match="user input"):
        Message(role=Role.ASSISTANT, tool_results=(ToolResult(call_id="t1", content="{}"),))
    with pytest.raises(ValueError, match="says nothing"):
        Message(role=Role.ASSISTANT, text="  ")


def test_a_token_count_is_a_non_negative_int_and_adds() -> None:
    with pytest.raises(ValueError, match="not a count"):
        TokenUsage(input_tokens=-1, output_tokens=0)
    with pytest.raises(TypeError, match="int"):
        TokenUsage(input_tokens=1.5, output_tokens=0)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="int"):
        TokenUsage(input_tokens=True, output_tokens=0)
    spent = TokenUsage(input_tokens=10, output_tokens=4) + TokenUsage(3, 2)
    assert (spent.input_tokens, spent.output_tokens, spent.total) == (13, 6, 19)


def test_a_request_opens_with_the_question_and_names_each_tool_once() -> None:
    tool = ToolSchema(name="get_cost", description="Cost.")
    with pytest.raises(ValueError, match="something to complete"):
        CompletionRequest(system="s", messages=(), tools=(), max_output_tokens=10)
    with pytest.raises(ValueError, match="opens with the question"):
        CompletionRequest(
            system="s",
            messages=(Message(role=Role.ASSISTANT, text="hello"),),
            tools=(),
            max_output_tokens=10,
        )
    with pytest.raises(ValueError, match="ambiguous"):
        CompletionRequest(system="s", messages=(_ask(),), tools=(tool, tool), max_output_tokens=10)
    with pytest.raises(ValueError, match="cut off"):
        CompletionRequest(system="s", messages=(_ask(),), tools=(), max_output_tokens=0)
    request = CompletionRequest(system="s", messages=(_ask(),), tools=(tool,), max_output_tokens=10)
    assert request.question == "What did we spend last month?"


def test_a_completion_asks_for_tools_exactly_when_it_stopped_for_them() -> None:
    usage = TokenUsage(input_tokens=5, output_tokens=5)
    asking = Message(role=Role.ASSISTANT, tool_calls=(ToolCall(call_id="t1", name="get_cost"),))
    with pytest.raises(ValueError, match="exactly when"):
        Completion(message=asking, stop_reason=StopReason.END_TURN, usage=usage)
    with pytest.raises(ValueError, match="exactly when"):
        Completion(
            message=Message(role=Role.ASSISTANT, text="done"),
            stop_reason=StopReason.TOOL_USE,
            usage=usage,
        )
    with pytest.raises(ValueError, match="assistant's turn"):
        Completion(message=_ask(), stop_reason=StopReason.END_TURN, usage=usage)
    assert (
        Completion(message=asking, stop_reason=StopReason.TOOL_USE, usage=usage).usage.total == 10
    )
