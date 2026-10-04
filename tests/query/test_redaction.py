"""Redaction: gitleaks' rules, what each does, and that nothing of a secret survives.

TASK-P7-013. Every sample is built at run time from pieces, so the secret scanner this
repository runs over its own files never sees a credential-shaped string in this one. A
test that exists to catch a secret should not be the reason the security gate fails.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from finops_core.domain.insight import Gap, Refusal
from finops_core.ports.llm import ToolSchema
from finops_fakes.llm import ForbiddenModel
from finops_query.insight import ToolOutput, ask
from finops_query.redaction import RULES, Action, scan, shannon

#: One sample per rule, as a credential of that kind would appear in a question.
SAMPLES: dict[str, str] = {
    "aws-access-token": "AKIA" + "Z7QW2XK4M6R3TP5B",
    "github-pat": "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
    "gitlab-pat": "glpat-" + "Xk9Lm3Np5Rs8Tv1Wy4Za",
    "stripe-access-token": "sk_" + "live_" + "4eC39HqLyjWDarjtT1zdp7dc",
    "slack-webhook-url": "https://hooks.slack.com/services/"
    + "T02ABCDEF/B03GHIJKL/"
    + "aB3dE5gH7jK9mN1pQ3sT5vW7",
    "jwt": "eyJ"
    + "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    + ".eyJ"
    + "zdWIiOiJhLXBlcnNvbiIsIm5hbWUiOiJhLW5hbWUifQ"
    + ".Qm9rT2hNc0pfV2tYcEZ6VjVHZ2RKcG5L",
    "private-key": "-----BEGIN "
    + "RSA PRIVATE KEY-----\n"
    + "MIIEowIBAAKCAQEA7yN8kXq3Lw2Zr5Vt9Pq1Hs6Gd4Jf8Km2Nb7Cx3Yz5Wa1Qe9R\n"
    + "-----END RSA PRIVATE KEY-----",
}

#: AWS documentation's own example key. gitleaks allowlists it and this does not.
DOCUMENTED_EXAMPLE = "AKIA" + "IOSFODNN7" + "EXAMPLE"


def question_holding(secret: str) -> str:
    return f"Our cost jumped on Tuesday. My credential is {secret} if that helps. Why?"


# --- the rules, and what each does -------------------------------------------------------


def test_there_is_a_sample_for_every_rule_and_a_rule_for_every_sample() -> None:
    assert set(SAMPLES) == {rule.rule_id for rule in RULES}


@pytest.mark.parametrize("rule", RULES, ids=lambda rule: rule.rule_id)
def test_each_rule_finds_its_secret_and_does_what_it_says(rule: Any) -> None:
    found = scan(question_holding(SAMPLES[rule.rule_id]))

    assert [(hit.rule_id, hit.action) for hit in found.hits] == [(rule.rule_id, rule.action)]
    assert SAMPLES[rule.rule_id] not in found.text
    assert f"[redacted: {rule.rule_id}]" in found.text
    assert found.text.startswith("Our cost jumped on Tuesday."), "the question around it stays"


def test_a_credential_that_grants_access_blocks_and_a_pasted_token_is_redacted() -> None:
    """Per rule, not global, the plan's second criterion."""
    actions = {rule.rule_id: rule.action for rule in RULES}
    assert actions["aws-access-token"] is Action.BLOCKED
    assert actions["private-key"] is Action.BLOCKED
    assert actions["jwt"] is Action.REDACTED
    assert actions["slack-webhook-url"] is Action.REDACTED
    assert scan(question_holding(SAMPLES["aws-access-token"])).blocked
    assert not scan(question_holding(SAMPLES["jwt"])).blocked


def test_a_match_below_the_entropy_floor_is_not_a_secret() -> None:
    """gitleaks' floor, kept: a run of one character is a pattern, not a credential."""
    flat = "ghp_" + "a" * 36
    assert shannon(flat[4:]) < 3.0
    assert scan(question_holding(flat)).hits == ()


def test_the_documented_example_key_is_withheld_although_gitleaks_would_pass_it() -> None:
    """The one deliberate difference. A question is not documentation."""
    found = scan(question_holding(DOCUMENTED_EXAMPLE))
    assert found.blocked
    assert DOCUMENTED_EXAMPLE not in found.text


def test_a_question_holding_no_secret_is_left_exactly_as_typed() -> None:
    typed = "  Which service cost the most last month?  "
    assert scan(typed).text == typed
    assert scan(typed).hits == ()


def test_a_hit_carries_the_rule_and_the_action_and_nothing_of_the_secret() -> None:
    (hit,) = scan(question_holding(SAMPLES["github-pat"])).hits
    assert vars(hit) == {"rule_id": "github-pat", "action": Action.BLOCKED}


# --- a blocked question reaches no model ---------------------------------------------------


class NoTools:
    def schemas(self) -> tuple[ToolSchema, ...]:
        return ()

    def call(self, name: str, arguments: Mapping[str, Any]) -> ToolOutput:
        raise AssertionError(f"a blocked question called {name} with {dict(arguments)}")


def test_a_blocked_question_is_refused_and_sent_nowhere() -> None:
    """The plan's third criterion, by a model that fails the test if it is asked anything."""
    exchange = ask(
        question_holding(SAMPLES["aws-access-token"]), model=ForbiddenModel(), toolbox=NoTools()
    )

    refusal = exchange.outcome
    assert isinstance(refusal, Refusal)
    assert refusal.gap is Gap.SECRET
    assert "aws-access-token" in refusal.reason
    assert SAMPLES["aws-access-token"] not in exchange.question
    assert SAMPLES["aws-access-token"] not in refusal.reason


# --- the same rules gitleaks runs ------------------------------------------------------------


@pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks is not installed here")
def test_gitleaks_itself_names_the_same_rule_for_every_sample(tmp_path: Path) -> None:
    """The fourth criterion: these are gitleaks' rules, and the binary agrees.

    Run over the samples with its default rules, the version `make security-scan` uses must
    report each one under the identifier this module gives it. A pattern copied wrongly, or
    one gitleaks has since changed, fails here rather than drifting silently.
    """
    for rule_id, sample in SAMPLES.items():
        (tmp_path / f"{rule_id}.txt").write_text(question_holding(sample) + "\n", encoding="utf-8")
    report = tmp_path / "report.json"

    subprocess.run(
        [
            "gitleaks",
            "dir",
            str(tmp_path),
            "--no-banner",
            "--report-format",
            "json",
            "--report-path",
            str(report),
            "--exit-code",
            "0",
        ],
        check=True,
        capture_output=True,
    )

    found = {
        (Path(finding["File"]).stem, finding["RuleID"])
        for finding in json.loads(report.read_text(encoding="utf-8"))
    }
    assert {(rule_id, rule_id) for rule_id in SAMPLES} <= found
