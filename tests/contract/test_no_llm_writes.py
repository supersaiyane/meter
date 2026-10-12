"""The assistant writes nothing to AWS and merges nothing anywhere. Constraint 6.

TASK-P7-014 and P7 spec section 15. `test_no_quota_writes.py` already asserts one absence by
name, and this file is a second because the subject and the failure differ: that one names
one API, and this one has to cover a remediation path that authors infrastructure code,
where the tempting shortcut is not a write API call at all but a `terraform apply` in a
subprocess, or a merge of the pull request the product just opened.

Four assertions, each in a place an absence can be undone:

1. No production module names a merge, an approve or an apply for a pull request, with
   comments and docstrings stripped first, for the reason `test_no_quota_writes.py` gives:
   the modules explain in prose that they never do it, and a grep would fail on that.
2. No production module starts `terraform`, `aws` or `kubectl` as a process.
3. The role Meter holds in a member account grants reads and nothing else, read from the
   template the StackSet deploys.
4. Authoring still works. A check that only forbids is satisfied by shipping nothing, so the
   capability it fences is asserted beside it.
"""

from __future__ import annotations

import ast
import pathlib
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from finops_core.domain.waste import WasteClass
from finops_fakes.pull_requests import RecordingPullRequests
from finops_query.remediation import Management, Proposed, RecommendationFacts, propose
from tests.contract.test_no_quota_writes import (
    _actions_in,
    code_only,
    member_role,
    production_sources,
)

#: Names a pull request is merged, approved or applied by, in the spellings the code hosts
#: and their client libraries use. Words in a sentence are not here, so the body that
#: promises never to merge can still say so.
PULL_REQUEST_WRITES = (
    "merge_pull_request",
    "MergePullRequest",
    "approve_pull_request",
    "ApprovePullRequest",
    "create_review",
    "submit_review",
    "enable_auto_merge",
    "auto_merge",
    "auto-approve",
    "terraform apply",
)

#: Tools that change a cloud or a cluster when started as a process.
FORBIDDEN_TOOLS = frozenset({"terraform", "aws", "kubectl"})

#: Every way a module here could start a process.
SPAWNERS = frozenset(
    {
        ("subprocess", "run"),
        ("subprocess", "Popen"),
        ("subprocess", "call"),
        ("subprocess", "check_call"),
        ("subprocess", "check_output"),
        ("os", "system"),
        ("os", "popen"),
        ("asyncio", "create_subprocess_exec"),
        ("asyncio", "create_subprocess_shell"),
    }
)

#: The verbs a read only role's actions may start with.
READ_VERBS = ("Describe", "Get", "List", "Select", "BatchGet", "Search", "Lookup")
#: Reads whose verb is not one of the above, each with the reason it changes nothing. IAM's service
#: authorization reference classes logs:StartQuery as Read: it runs a Logs Insights query over
#: events already written and creates, changes and removes no resource. TASK-P13-003, FEAT-082.
READS_BY_ANOTHER_VERB = frozenset({"logs:StartQuery"})


def spawned(source: str) -> Iterator[str]:
    """What each process a module starts is, by its first word, or why it cannot be told."""
    for node in ast.walk(ast.parse(source)):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and (node.func.value.id, node.func.attr) in SPAWNERS
        ):
            continue
        first = node.args[0] if node.args else None
        if isinstance(first, ast.List | ast.Tuple) and first.elts:
            head = first.elts[0]
            word = head.value if isinstance(head, ast.Constant) else None
        elif isinstance(first, ast.Constant) and isinstance(first.value, str):
            word = first.value.split()[0] if first.value.split() else None
        else:
            word = None
        # A command this cannot read is reported rather than trusted.
        yield pathlib.PurePath(word).name if isinstance(word, str) else "an unreadable command"


# --- what must stay absent -----------------------------------------------------------------


@pytest.mark.parametrize("name", PULL_REQUEST_WRITES)
def test_no_production_module_merges_approves_or_applies(name: str) -> None:
    offenders = [
        str(path) for path in production_sources() if name in code_only(path.read_text("utf-8"))
    ]
    assert offenders == [], f"{name} appears in production code: {offenders}"


def test_no_production_module_starts_a_tool_that_changes_a_cloud() -> None:
    started = {
        str(path): tool
        for path in production_sources()
        for tool in spawned(path.read_text(encoding="utf-8"))
        if tool in FORBIDDEN_TOOLS or tool == "an unreadable command"
    }
    assert started == {}


def test_the_member_role_grants_reads_and_nothing_else() -> None:
    """The hub can act in a member account only through this role, so this is the whole of
    what Meter could ever do there."""
    actions = _actions_in(member_role())
    assert actions, "no IAM actions were found in the member template, so this proves nothing"
    granted = actions - {"sts:AssumeRole"} - READS_BY_ANOTHER_VERB
    writes = sorted(a for a in granted if not a.split(":")[-1].startswith(READ_VERBS))
    assert writes == [], f"the member role grants more than reads: {writes}"
    assert "*" not in actions and not any(a.endswith(":*") for a in actions)


# --- the checks can fire ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "found"),
    [
        ('import subprocess\nsubprocess.run(["terraform", "apply"])\n', ["terraform"]),
        ('import os\nos.system("kubectl delete pod web")\n', ["kubectl"]),
        ('import subprocess\nsubprocess.run(["/usr/local/bin/aws", "s3", "rm"])\n', ["aws"]),
        ("import subprocess\nsubprocess.run(command)\n", ["an unreadable command"]),
        ('import subprocess\nsubprocess.run(["git", "status"])\n', ["git"]),
    ],
)
def test_the_process_scan_sees_what_it_is_looking_for(source: str, found: list[str]) -> None:
    """The positive case, so the absence above cannot be the scanner seeing nothing."""
    assert list(spawned(source)) == found


def test_the_name_scan_sees_a_merge_in_code_and_ignores_one_in_prose() -> None:
    assert "merge_pull_request" in code_only("client.merge_pull_request(number)\n")
    assert "merge_pull_request" not in code_only('"""We never call merge_pull_request."""\n')


# --- and the thing it fences still works --------------------------------------------------


def test_a_remediation_is_still_authored_and_opened_for_review() -> None:
    """Forbidding the write must not have been satisfied by removing the feature."""
    host = RecordingPullRequests()
    recommendation = RecommendationFacts(
        recommendation_id="rec-7",
        waste_class=WasteClass.NAT_GATEWAY_IDLE,
        resource_id="nat-0a1b2c3d4e5f60718",
        sub_account_id="fake-platform-a",
        region_id="eu-west-1",
        estimated_monthly_saving=Decimal("32.85"),
        confidence="HIGH",
        rationale="No bytes processed in the observation window.",
        as_of=datetime(2026, 9, 30, tzinfo=UTC),
    )

    proposed = propose(
        recommendation,
        Management(address="module.network.aws_nat_gateway.spare", state_reference="s3://state"),
        "narrow",
        host,
    )

    assert isinstance(proposed, Proposed)
    assert len(host.drafts) == 1
    assert "removed {" in host.drafts[0].changes[0].content
