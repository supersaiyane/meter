"""An AI provider's admin key, read from Secrets Manager under one path only. TASK-P13-004.

P13 plan rule 2: the key is read when it is needed and from nowhere but `meter/<env>/ai/`. The
reader refuses any other name before a call is made, and the hub's task role is granted that path
and no wider, which the last test reads out of the Terraform.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError

from finops_core import errors
from finops_providers.aws.secrets import (
    AiKeyReader,
    CodeHostKeyReader,
    ai_key_prefix,
    codehost_key_prefix,
)

ROOT = Path(__file__).resolve().parents[3]
NAME = "meter/dev/ai/openai-platform"


class StubSecrets:
    def __init__(self, answer: dict[str, Any] | Exception) -> None:
        self.answer = answer
        self.asked: list[str] = []

    def get_secret_value(self, *, SecretId: str) -> dict[str, Any]:  # noqa: N803 - boto3's name
        self.asked.append(SecretId)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def read(client: StubSecrets, name: str = NAME) -> str:
    return AiKeyReader("dev", client).reader(name, scope_key="openai:org-x", collector="c")()


def refused(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, "GetSecretValue")


def test_the_key_is_read_from_the_secret_it_names() -> None:
    client = StubSecrets({"SecretString": "  the-key \n"})
    assert read(client) == "the-key"
    assert client.asked == [NAME]


def test_nothing_is_read_until_the_key_is_needed() -> None:
    client = StubSecrets({"SecretString": "k"})
    AiKeyReader("dev", client).reader(NAME, scope_key="s", collector="c")
    assert client.asked == []


@pytest.mark.parametrize(
    "name", ["meter/prod/ai/openai", "meter/dev/database", "other/dev/ai/x", "meter/dev/aix/y"]
)
def test_a_name_outside_this_environments_ai_path_is_refused_before_any_call(name: str) -> None:
    client = StubSecrets({"SecretString": "k"})
    with pytest.raises(errors.Misconfigured, match="meter/dev/ai/"):
        read(client, name)
    assert client.asked == []


@pytest.mark.parametrize(
    ("answer", "cause", "says"),
    [
        (refused("ResourceNotFoundException"), errors.Misconfigured, "no secret named"),
        (refused("AccessDeniedException"), errors.AccessDenied, "AccessDenied"),
        (refused("ThrottlingException"), errors.Throttled, "Throttling"),
        ({"SecretString": "   "}, errors.Misconfigured, "holds no key"),
        ({"SecretBinary": b"k"}, errors.Misconfigured, "holds no key"),
    ],
)
def test_a_key_that_cannot_be_read_fails_typed(
    answer: Any, cause: type[errors.CollectionError], says: str
) -> None:
    with pytest.raises(cause, match=says):
        read(StubSecrets(answer))


def test_the_path_is_the_environments() -> None:
    assert ai_key_prefix("prod") == "meter/prod/ai/"


@pytest.mark.parametrize(
    ("sid", "path"),
    [("ReadTheAiProviderKeys", "ai"), ("ReadTheCodeHostKey", "codehost")],
)
def test_the_task_role_may_read_each_key_path_and_no_wider(sid: str, path: str) -> None:
    iam = (ROOT / "infra" / "terraform" / "hub" / "iam.tf").read_text(encoding="utf-8")
    statement = re.search(rf'sid\s+=\s+"{sid}"(.*?)\n  \}}', iam, re.DOTALL)
    assert statement is not None
    (resource,) = re.findall(r'resources\s+=\s+\["([^"]+)"\]', statement.group(1))
    assert resource.endswith(f":secret:meter/${{var.env}}/{path}/*")
    assert re.findall(r'actions\s+=\s+\["([^"]+)"\]', statement.group(1)) == [
        "secretsmanager:GetSecretValue"
    ]


# --- the code host app's private key, P15, TASK-P15-002 ------------------------------------------

CODEHOST = "meter/dev/codehost/github-app"


def test_the_code_host_key_is_read_from_its_own_path_and_no_other() -> None:
    client = StubSecrets(
        {"SecretString": "-----BEGIN PRIVATE KEY-----\nk\n-----END PRIVATE KEY-----\n"}
    )
    keys = CodeHostKeyReader("dev", client)
    assert keys.reader(CODEHOST, scope_key="github:acme/infra", collector="c")().startswith(
        "-----BEGIN PRIVATE KEY-----"
    )
    with pytest.raises(errors.Misconfigured, match="the code host app's private key"):
        keys.reader(NAME, scope_key="github:acme/infra", collector="c")()
    assert client.asked == [CODEHOST]
    assert codehost_key_prefix("prod") == "meter/prod/codehost/"


def test_a_missing_code_host_key_says_how_to_make_it() -> None:
    keys = CodeHostKeyReader("dev", StubSecrets(refused("ResourceNotFoundException")))
    with pytest.raises(errors.Misconfigured, match="GitHub App's private key"):
        keys.reader(CODEHOST, scope_key="github:acme/infra", collector="c")()
