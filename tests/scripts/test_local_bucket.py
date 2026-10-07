"""The local stack's data bucket, made in LocalStack and nowhere else. FEAT-069, TASK-P8-011.

The refusal is held first, because it is the half that matters: an endpoint that is not
LocalStack on a local host makes nothing, whatever credentials are present.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import boto3
import pytest
from botocore.stub import Stubber

# Loaded by path, as the other script tests load theirs: `scripts` is not a package.
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "local_bucket.py"
spec = importlib.util.spec_from_file_location("local_bucket", SCRIPT)
assert spec and spec.loader
local_bucket = importlib.util.module_from_spec(spec)
sys.modules["local_bucket"] = local_bucket
spec.loader.exec_module(local_bucket)

BUCKET = "meter-data-test"
REGION = "eu-west-1"


def s3() -> Any:
    return boto3.client(
        "s3", region_name=REGION, aws_access_key_id="test", aws_secret_access_key="test"
    )


@pytest.mark.parametrize(
    ("endpoint", "local"),
    [
        ("http://localhost:9734", True),
        ("http://localstack:4566", True),
        ("http://127.0.0.1:9734", True),
        ("https://s3.amazonaws.com", False),
        ("https://localhost.attacker.example", False),
        ("", False),
    ],
)
def test_only_localstack_on_a_local_host_is_used(
    monkeypatch: pytest.MonkeyPatch, endpoint: str, local: bool
) -> None:
    monkeypatch.setenv("AWS_ENDPOINT_URL", endpoint)
    assert (local_bucket.local_endpoint() is not None) is local


def test_a_bucket_that_is_not_there_is_made() -> None:
    client = s3()
    with Stubber(client) as stub:
        stub.add_client_error("head_bucket", service_error_code="404", http_status_code=404)
        stub.add_response(
            "create_bucket",
            {},
            {"Bucket": BUCKET, "CreateBucketConfiguration": {"LocationConstraint": REGION}},
        )
        assert local_bucket.ensure(client, BUCKET) is True
        stub.assert_no_pending_responses()


def test_a_bucket_that_is_there_is_left_alone() -> None:
    client = s3()
    with Stubber(client) as stub:
        stub.add_response("head_bucket", {}, {"Bucket": BUCKET})
        assert local_bucket.ensure(client, BUCKET) is False
        stub.assert_no_pending_responses()


def test_a_remote_endpoint_is_refused_before_anything_is_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AWS_ENDPOINT_URL", "https://s3.eu-west-1.amazonaws.com")
    monkeypatch.setattr(
        local_bucket, "load_settings", lambda: pytest.fail("settings were read before refusing")
    )
    assert local_bucket.main() == 2
    assert "REFUSED" in capsys.readouterr().out


def test_the_default_region_is_made_without_a_constraint() -> None:
    """S3 refuses us-east-1 as a location constraint, so a bucket there is made without one."""
    client = boto3.client(
        "s3", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test"
    )
    with Stubber(client) as stub:
        stub.add_client_error("head_bucket", service_error_code="404", http_status_code=404)
        stub.add_response("create_bucket", {}, {"Bucket": BUCKET})
        assert local_bucket.ensure(client, BUCKET) is True
        stub.assert_no_pending_responses()
