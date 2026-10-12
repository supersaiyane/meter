"""The queue between the dispatcher and the worker, over SQS. TASK-P12-003, FEAT-079.

P12 spec section 5.3 and the plan's criteria: a unit survives the round trip unchanged, under moto,
and a message the worker cannot decode is logged and left for the redrive, never dropped.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import boto3
import pytest
from moto import mock_aws

from finops_core.domain.account import AccountKey, Provider
from finops_ingest.dispatcher import Dispatcher, WorkUnit
from finops_ingest.registry import CollectorRegistry
from finops_ingest.sqs import (
    BATCH,
    VERSION,
    Delivery,
    SqsConsumer,
    SqsPublisher,
    UndecodableMessageError,
    decode,
    encode,
)

REGION = "eu-west-1"
TENANT = UUID("6f1c2b0e-0000-4000-8000-000000000001")
START = datetime(2026, 10, 12, 0, 0, tzinfo=UTC)
END = datetime(2026, 10, 12, 6, 0, tzinfo=UTC)
ORGANIZATION = WorkUnit(tenant_id=TENANT, collector="org_tree", window_start=START, window_end=END)
ACCOUNT = WorkUnit(
    tenant_id=TENANT,
    collector="quotas",
    window_start=START,
    window_end=END,
    account=AccountKey(provider=Provider.AWS, account_id="111111111111"),
    region=REGION,
)


@pytest.fixture
def queue() -> Iterator[SimpleNamespace]:
    """A work queue redriving to a dead letter queue after two receives, as the hub's does."""
    with mock_aws():
        client = boto3.client("sqs", region_name=REGION)
        dead = client.create_queue(QueueName="meter-test-work-dlq")["QueueUrl"]
        dead_arn = client.get_queue_attributes(QueueUrl=dead, AttributeNames=["QueueArn"])[
            "Attributes"
        ]["QueueArn"]
        work = client.create_queue(
            QueueName="meter-test-work",
            Attributes={
                "VisibilityTimeout": "0",
                "RedrivePolicy": json.dumps(
                    {"deadLetterTargetArn": dead_arn, "maxReceiveCount": "2"}
                ),
            },
        )["QueueUrl"]
        yield SimpleNamespace(client=client, url=work, dead=dead)


def consumer(queue: SimpleNamespace) -> SqsConsumer:
    return SqsConsumer(queue.client, queue.url, wait_seconds=0)


def waiting(queue: SimpleNamespace, url: str) -> int:
    attributes = queue.client.get_queue_attributes(
        QueueUrl=url,
        AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"],
    )["Attributes"]
    return int(attributes["ApproximateNumberOfMessages"]) + int(
        attributes["ApproximateNumberOfMessagesNotVisible"]
    )


def test_a_unit_survives_the_round_trip_unchanged(queue: SimpleNamespace) -> None:
    publisher = SqsPublisher(queue.client, queue.url)
    assert publisher.publish(ORGANIZATION)
    assert publisher.publish(ACCOUNT)
    received = consumer(queue).receive()
    assert received.undecodable == 0
    assert sorted((one.unit for one in received.deliveries), key=lambda u: u.collector) == [
        ORGANIZATION,
        ACCOUNT,
    ]
    assert {one.attempt for one in received.deliveries} == {1}


def test_one_dispatch_never_sends_the_same_unit_twice(queue: SimpleNamespace) -> None:
    dispatcher = Dispatcher(CollectorRegistry(), SqsPublisher(queue.client, queue.url))
    result = dispatcher.dispatch([ORGANIZATION, ACCOUNT, ORGANIZATION])
    assert (result.published, result.deduplicated) == (2, 1)
    assert waiting(queue, queue.url) == 2


def test_two_tenants_with_the_same_unit_are_both_sent(queue: SimpleNamespace) -> None:
    other = WorkUnit(
        tenant_id=UUID("6f1c2b0e-0000-4000-8000-000000000002"),
        collector=ORGANIZATION.collector,
        window_start=START,
        window_end=END,
    )
    assert other.dedup_key == ORGANIZATION.dedup_key, "the ledger's key holds no tenant"
    publisher = SqsPublisher(queue.client, queue.url)
    assert publisher.publish(ORGANIZATION)
    assert publisher.publish(other), "ISS-275: refused as a duplicate of another tenant's"
    assert waiting(queue, queue.url) == 2


def test_a_settled_delivery_is_deleted(queue: SimpleNamespace) -> None:
    SqsPublisher(queue.client, queue.url).publish(ACCOUNT)
    reader = consumer(queue)
    assert reader.delete(reader.receive().deliveries) == ()
    assert reader.receive().deliveries == ()
    assert waiting(queue, queue.url) == 0


def test_a_message_it_cannot_decode_is_logged_and_left_for_the_redrive(
    queue: SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    queue.client.send_message(QueueUrl=queue.url, MessageBody="not a unit")
    reader = consumer(queue)
    with caplog.at_level(logging.ERROR, logger="finops_ingest.sqs"):
        first = reader.receive()
    assert (first.deliveries, first.undecodable) == ((), 1)
    (record,) = caplog.records
    assert record.receive_count == 1  # type: ignore[attr-defined]
    assert "not JSON" in record.reason  # type: ignore[attr-defined]
    assert record.message_id  # type: ignore[attr-defined]

    second = reader.receive()
    assert second.undecodable == 1, "still on the queue, received again"
    reader.receive()
    (moved,) = queue.client.receive_message(QueueUrl=queue.dead)["Messages"]
    assert moved["Body"] == "not a unit", "the redrive moved it to the dead letter queue intact"


def test_a_good_unit_beside_a_bad_one_is_still_delivered(queue: SimpleNamespace) -> None:
    queue.client.send_message(QueueUrl=queue.url, MessageBody=json.dumps({"version": 99}))
    SqsPublisher(queue.client, queue.url).publish(ACCOUNT)
    received = consumer(queue).receive()
    assert [one.unit for one in received.deliveries] == [ACCOUNT]
    assert received.undecodable == 1


def test_a_refused_delete_is_returned_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    deliveries = tuple(
        Delivery(unit=ACCOUNT, receipt=f"r{index}", attempt=1, message_id=f"m{index}")
        for index in range(BATCH + 2)
    )
    calls: list[list[dict[str, str]]] = []

    def delete_message_batch(**request: Any) -> dict[str, Any]:
        calls.append(request["Entries"])
        refused = [{"Id": "1", "Code": "ReceiptHandleIsInvalid"}] if len(calls) == 2 else []
        return {"Failed": refused}

    reader = SqsConsumer(SimpleNamespace(delete_message_batch=delete_message_batch), "url")
    with caplog.at_level(logging.WARNING, logger="finops_ingest.sqs"):
        assert reader.delete(deliveries) == (f"m{BATCH + 1}",)
    assert [len(entries) for entries in calls] == [BATCH, 2]
    assert caplog.records[0].code == "ReceiptHandleIsInvalid"  # type: ignore[attr-defined]


def test_a_receive_asks_for_at_most_a_batch_and_for_the_receive_count() -> None:
    asked: dict[str, Any] = {}

    def receive_message(**request: Any) -> dict[str, Any]:
        asked.update(request)
        return {}

    received = SqsConsumer(SimpleNamespace(receive_message=receive_message), "url").receive(50)
    assert received.deliveries == ()
    assert asked["MaxNumberOfMessages"] == BATCH
    assert asked["WaitTimeSeconds"] == 20
    assert asked["MessageSystemAttributeNames"] == ["ApproximateReceiveCount"]


def test_a_message_names_its_version() -> None:
    assert json.loads(encode(ACCOUNT))["version"] == VERSION


def body(**overrides: Any) -> str:
    message = json.loads(encode(ACCOUNT))
    message.update(overrides)
    return json.dumps(message)


@pytest.mark.parametrize(
    ("raw", "why"),
    [
        ("{", "not JSON"),
        ("[]", "not a JSON object"),
        (body(version=2), "version 2"),
        (body(collector=""), "collector"),
        (body(tenant_id="not a uuid"), "badly formed"),
        (body(window_start="2026-10-12T00:00:00"), "no time zone"),
        (body(window_end="yesterday"), "isoformat"),
        (body(account={"provider": "nimbus", "account_id": "1"}), "nimbus"),
        (body(account="111111111111"), "account is not an object"),
        (body(region=7), "region"),
    ],
)
def test_a_body_that_is_not_a_unit_is_undecodable_saying_why(raw: str, why: str) -> None:
    with pytest.raises(UndecodableMessageError, match=why):
        decode(raw)
