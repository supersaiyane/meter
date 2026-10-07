"""The report store in the hub's data bucket. FEAT-069, TASK-P8-011.

Stubbed with botocore's `Stubber` over a real client, so every call the adapter makes is checked
against S3's own service model, parameter names and all, and nothing reaches the network.
"""

from __future__ import annotations

import io
from typing import Any

import boto3
import pytest
from botocore.exceptions import EndpointConnectionError
from botocore.response import StreamingBody
from botocore.stub import Stubber

from finops_core.config import Settings
from finops_core.errors import AccessDenied, NoData, Unreachable
from finops_providers.aws.report_store import S3ReportStore

BUCKET = "meter-data-test"
KEY = "reports/5eeded00-0000-4000-8000-000000000001/4c1b5e2a-0000-4000-8000-000000000002.xlsx"
BODY = b"cells"


def s3() -> Any:
    return boto3.client(
        "s3",
        region_name="eu-west-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def test_a_file_is_put_under_its_key_with_its_type() -> None:
    client = s3()
    with Stubber(client) as stub:
        stub.add_response(
            "put_object",
            {},
            {"Bucket": BUCKET, "Key": KEY, "Body": BODY, "ContentType": "text/csv"},
        )
        S3ReportStore(client, BUCKET).put(KEY, BODY, "text/csv")
        stub.assert_no_pending_responses()


def test_a_file_is_read_back_by_its_key() -> None:
    client = s3()
    with Stubber(client) as stub:
        stub.add_response(
            "get_object",
            {"Body": StreamingBody(io.BytesIO(BODY), len(BODY))},
            {"Bucket": BUCKET, "Key": KEY},
        )
        assert S3ReportStore(client, BUCKET).get(KEY) == BODY


def test_a_key_with_nothing_under_it_is_no_data_never_an_empty_file() -> None:
    client = s3()
    with Stubber(client) as stub:
        stub.add_client_error(
            "get_object",
            service_error_code="NoSuchKey",
            http_status_code=404,
            expected_params={"Bucket": BUCKET, "Key": KEY},
        )
        with pytest.raises(NoData) as missing:
            S3ReportStore(client, BUCKET).get(KEY)
    assert BUCKET in missing.value.scope_key


@pytest.mark.parametrize("operation", ["put_object", "get_object"])
def test_a_refusal_is_access_denied(operation: str) -> None:
    client = s3()
    store = S3ReportStore(client, BUCKET)
    with Stubber(client) as stub:
        stub.add_client_error(operation, service_error_code="AccessDenied", http_status_code=403)
        with pytest.raises(AccessDenied):
            if operation == "put_object":
                store.put(KEY, BODY, "text/csv")
            else:
                store.get(KEY)


class Unreachable_S3:  # noqa: N801
    """A client whose every call finds no endpoint, as a network with no route to S3 does."""

    def put_object(self, **_: Any) -> None:
        raise EndpointConnectionError(endpoint_url="https://s3.eu-west-1.amazonaws.com")

    def get_object(self, **_: Any) -> None:
        raise EndpointConnectionError(endpoint_url="https://s3.eu-west-1.amazonaws.com")


def test_a_store_that_cannot_be_reached_says_so_both_ways() -> None:
    store = S3ReportStore(Unreachable_S3(), BUCKET)
    with pytest.raises(Unreachable):
        store.put(KEY, BODY, "text/csv")
    with pytest.raises(Unreachable):
        store.get(KEY)


def test_the_store_the_api_writes_to_is_the_data_bucket_the_settings_name(
    settings: Settings,
) -> None:
    store = S3ReportStore.from_settings(settings.model_copy(update={"s3_bucket": BUCKET}))
    assert store._bucket == BUCKET
