"""Meter has never written into a member account, and this keeps that true of quotas.

Constraint 6 and P5 spec section 6. The decision was taken on 2026-09-20 and the reasoning is
not squeamishness about this particular call, which is close to harmless. It is that the read
only property is worth more than any single feature it costs: a product that has never written
into a customer account can say so in one sentence, and every security review after that is
shorter. The first exception ends that, and the second is always easier to argue than the
first.

So this file asserts an absence, in the two places an absence can be undone.

**The API name appears nowhere in production code.** `RequestServiceQuotaIncrease` is the call,
and a contributor who adds it fails a test whose name explains why they should not. The name is
searched for rather than the behaviour, because behaviour is what a mock can be made to pass
and a string cannot.

**The IAM policy does not grant it.** A test over the Terraform, because the code not making a
call and the role not permitting it are independent facts, and the second is the one that still
holds when somebody adds a dependency that makes calls of its own.

The CLI spelling, `request-service-quota-increase`, is deliberately allowed and is deliberately
a different string. `finops_query/quota.py` emits it for a person to paste, which is a
different act under different credentials from a call Meter makes under an assumed role.
Collapsing the two spellings into one check would mean either forbidding the draft or
permitting the call.
"""

from __future__ import annotations

import ast
import io
import pathlib
import tokenize
from typing import Any

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

#: The API this product does not call, exactly as botocore spells the operation.
FORBIDDEN_API = "RequestServiceQuotaIncrease"

#: The CLI form, which is allowed and is what a draft renders for a person to run.
PERMITTED_CLI = "request-service-quota-increase"

#: Everything that ships. The fakes are excluded because they ship nothing, per ADR-0022, and
#: the tests are excluded because this file itself has to be able to name the string.
PRODUCTION_PACKAGES = (
    "finops_core",
    "finops_providers",
    "finops_ingest",
    "finops_query",
    "finops_api",
    "finops_mcp",
)

MEMBER_ROLE = ROOT / "infra" / "terraform" / "member" / "collector_role.yaml"

#: Every write shaped quota call, named so the next one is a decision rather than a slip. All
#: four change something in a member account and none of them is in the product. The three
#: template calls set organization wide defaults, which is a write into every member account at
#: once rather than into one, and spec section 6 treats them the same way: Meter renders the
#: template it would set and does not set it.
QUOTA_WRITES = (
    "RequestServiceQuotaIncrease",
    "PutServiceQuotaIncreaseRequestIntoTemplate",
    "DeleteServiceQuotaIncreaseRequestFromTemplate",
    "AssociateServiceQuotaTemplate",
)


class _Tolerant(yaml.SafeLoader):  # type: ignore[misc]
    """A loader that reads CloudFormation rather than refusing it.

    `collector_role.yaml` is a CloudFormation template, so it carries intrinsics like
    `!GetAtt` and `!Sub`, which `safe_load` refuses outright. Tolerating unknown tags is the
    right trade here: this test reads one key, `Action`, and none of the intrinsics appear in
    one. The alternative, parsing the file as text, would make the check pass on a policy whose
    structure had changed out from under it.
    """


def _ignore_unknown(loader: yaml.SafeLoader, tag_suffix: str, node: yaml.Node) -> object:
    del loader, tag_suffix
    return f"<{node.tag}>"


_Tolerant.add_multi_constructor("!", _ignore_unknown)


def member_role() -> Any:
    return yaml.load(MEMBER_ROLE.read_text(encoding="utf-8"), Loader=_Tolerant)


def code_only(source: str) -> str:
    """The source with its comments and docstrings removed.

    The plan asks for an occurrence "outside a comment or a test", and that distinction is not
    pedantic: every module in this sub project explains in its own docstring that it does not
    call the API, which means the explanation contains the string. A grep would fail on the
    documentation of the very decision it exists to protect, and the obvious fix, deleting the
    explanation, would be the worst possible response to the check.

    So comments and docstrings go and everything else stays. A string literal that is not a
    docstring survives, which is deliberate: `"RequestServiceQuotaIncrease"` passed to a client
    is exactly the call being forbidden, and it is spelled as a string.
    """
    tree = ast.parse(source)
    prose: set[tuple[int, int]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        first = node.body[0] if node.body else None
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            prose.add((first.lineno, first.col_offset))

    kept: list[str] = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            continue
        if token.type == tokenize.STRING and token.start in prose:
            continue
        kept.append(token.string)
    return "\n".join(kept)


def names_the_api(path: pathlib.Path, api: str) -> bool:
    return api in code_only(path.read_text(encoding="utf-8"))


def production_sources() -> list[pathlib.Path]:
    found = [
        path for package in PRODUCTION_PACKAGES for path in sorted((ROOT / package).rglob("*.py"))
    ]
    assert found, "no production source was found, so every assertion below would be vacuous"
    return found


def test_no_production_module_names_the_quota_increase_api() -> None:
    """Meter drafts a quota increase and hands it to a person. It never submits one.

    If this fails, the question is not how to make it pass. It is whether constraint 6 is being
    changed, which needs an ADR superseding it, because the sentence "this product has never
    written into a customer account" is worth more than the paste it saves. P5 spec section 6
    argues it properly and exists so that conversation starts from the reasoning.
    """
    offenders = [
        str(path.relative_to(ROOT))
        for path in production_sources()
        if names_the_api(path, FORBIDDEN_API)
    ]
    assert not offenders, (
        f"{FORBIDDEN_API} appears in {offenders}. That call writes into a member account, which "
        f"constraint 6 forbids in v1. Meter drafts the request and a person submits it: see "
        f"finops_query/quota.py and P5 spec section 6."
    )


@pytest.mark.parametrize("api", QUOTA_WRITES)
def test_no_production_module_names_any_quota_write(api: str) -> None:
    """The template calls too, for the reason given beside `QUOTA_WRITES`."""
    offenders = [
        str(path.relative_to(ROOT)) for path in production_sources() if names_the_api(path, api)
    ]
    assert not offenders, f"{api} writes into a member account and appears in {offenders}"


def test_the_cli_form_is_allowed_and_is_actually_emitted() -> None:
    """The other half, without which the test above could be satisfied by deleting the feature.

    A check that only forbids can be passed by shipping nothing. This asserts the draft exists
    and that what it emits is the CLI spelling, so the absence above is an absence of the call
    rather than an absence of the capability.
    """
    from decimal import Decimal

    from finops_query.quota import IncreaseDraft, draft_for

    draft = draft_for(
        service_code="ec2",
        quota_code="L-1216C47A",
        region_id="eu-west-1",
        current_limit=Decimal("320"),
        observed_usage=Decimal("307"),
        is_adjustable=True,
    )
    assert isinstance(draft, IncreaseDraft)
    assert PERMITTED_CLI in draft.cli_command
    assert FORBIDDEN_API not in draft.cli_command
    assert draft.console_url.startswith("https://")


def test_the_org_reader_role_does_not_grant_the_increase() -> None:
    """The permission is not there to be misused later. Spec section 10.

    Independent of the tests above, and that independence is the point: the code not making a
    call and the role not permitting it fail separately.
    """
    actions = _actions_in(member_role())
    assert actions, "no IAM actions were found in the member template, so this proves nothing"
    for api in QUOTA_WRITES:
        assert f"servicequotas:{api}" not in actions, f"the member role grants {api}"
    # Also refuse the wildcards that would grant it without naming it, which is how a policy
    # acquires a write nobody reviewed.
    for wildcard in ("servicequotas:*", "*"):
        assert wildcard not in actions, f"the member role grants {wildcard}"


def test_the_org_reader_role_does_grant_the_reads_the_collector_needs() -> None:
    """The same argument as the CLI test: a policy with nothing in it would pass the one above.

    These four are what `finops_providers/aws/quotas.py` actually calls, so a policy that lost
    one of them fails here rather than on a collection somebody has to debug.
    """
    actions = _actions_in(member_role())
    for needed in (
        "servicequotas:ListServices",
        "servicequotas:ListServiceQuotas",
        "servicequotas:ListRequestedServiceQuotaChangeHistory",
        "cloudwatch:GetMetricData",
    ):
        assert needed in actions, f"the member role does not grant {needed}"


def _actions_in(node: object) -> set[str]:
    """Every IAM action in the template, wherever the statements happen to be nested.

    Walked rather than indexed, because a path into the document would silently stop finding
    anything the day a statement moved, and a check that finds nothing reports success.
    """
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "Action":
                if isinstance(value, str):
                    found.add(value)
                elif isinstance(value, list):
                    found.update(str(one) for one in value)
            found |= _actions_in(value)
    elif isinstance(node, list):
        for one in node:
            found |= _actions_in(one)
    return found
