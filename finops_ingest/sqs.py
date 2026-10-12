"""The queue between the dispatcher and the worker, over SQS. FEAT-079, TASK-P12-003.

P12 spec section 5.3. The dispatcher publishes each unit as one message and the worker receives
them in batches. The client is handed in, a boto3 SQS client in a deployment, LocalStack's in the
local stack and moto's in the tests, so this module makes no client and holds no credential.

**The hub's queue is a standard queue**, not FIFO, `infra/terraform/hub/queue.tf`, so SQS may
deliver a message more than once and deduplicates nothing. A unit delivered twice is made free by
the run ledger, whose claim keys on the unit's dedup key; the publisher also refuses a unit it has
already sent in this dispatch, so one dispatch never sends the same unit twice.

**A message that cannot be decoded is never dropped.** It is logged with its id and how often it
has been received, and left on the queue: its visibility lapses, it is received again, and after
the queue's maxReceiveCount SQS moves it to the dead letter queue, where somebody can read it. A
worker that deleted what it could not read would lose a unit without a trace.

**A message names its version**, because during a rolling deploy an old worker and a new one read
the same queue, constraint 12. A version this code does not know is undecodable, which is the safe
reading: left for the redrive rather than guessed at.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from finops_core.domain.account import AccountKey, Provider
from finops_ingest.dispatcher import WorkUnit

LOGGER = logging.getLogger(__name__)

#: The message format this code writes and reads.
VERSION: Final = 1
#: The most messages SQS returns, or deletes, in one call.
BATCH: Final = 10
#: The longest SQS holds a receive open waiting for a message, in seconds.
LONG_POLL_SECONDS: Final = 20


class UndecodableMessageError(ValueError):
    """A message body that is not a unit this code can read."""


def encode(unit: WorkUnit) -> str:
    """One unit as a message body."""
    account = (
        None
        if unit.account is None
        else {"provider": unit.account.provider.value, "account_id": unit.account.account_id}
    )
    return json.dumps(
        {
            "version": VERSION,
            "tenant_id": str(unit.tenant_id),
            "collector": unit.collector,
            "window_start": unit.window_start.isoformat(),
            "window_end": unit.window_end.isoformat(),
            "account": account,
            "region": unit.region,
        },
        sort_keys=True,
    )


def decode(body: str) -> WorkUnit:
    """A message body as the unit it names, or UndecodableMessageError saying why not."""
    try:
        message = json.loads(body)
    except json.JSONDecodeError as failure:
        raise UndecodableMessageError(f"not JSON: {failure.msg}") from failure
    if not isinstance(message, dict):
        raise UndecodableMessageError("not a JSON object")
    if message.get("version") != VERSION:
        raise UndecodableMessageError(
            f"version {message.get('version')!r}, and this worker reads version {VERSION}"
        )
    try:
        return WorkUnit(
            tenant_id=UUID(_text(message, "tenant_id")),
            collector=_text(message, "collector"),
            window_start=_instant(message, "window_start"),
            window_end=_instant(message, "window_end"),
            account=_account(message.get("account")),
            region=_optional_text(message, "region"),
        )
    except (KeyError, TypeError, ValueError) as failure:
        raise UndecodableMessageError(str(failure)) from failure


def _text(message: Mapping[str, Any], key: str) -> str:
    value = message[key]
    if not isinstance(value, str) or not value:
        raise UndecodableMessageError(f"{key} is not a non empty string")
    return value


def _optional_text(message: Mapping[str, Any], key: str) -> str | None:
    return None if message.get(key) is None else _text(message, key)


def _instant(message: Mapping[str, Any], key: str) -> datetime:
    instant = datetime.fromisoformat(_text(message, key))
    if instant.tzinfo is None:
        raise UndecodableMessageError(f"{key} has no time zone")
    return instant


def _account(raw: Any) -> AccountKey | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise UndecodableMessageError("account is not an object")
    return AccountKey(
        provider=Provider(_text(raw, "provider")), account_id=_text(raw, "account_id")
    )


@dataclass(frozen=True)
class Delivery:
    """One unit as SQS delivered it: what to delete it by, and how often it has been received."""

    unit: WorkUnit
    receipt: str
    attempt: int
    message_id: str


@dataclass(frozen=True)
class Received:
    """One receive: the units it carried, and how many messages could not be read."""

    deliveries: tuple[Delivery, ...]
    undecodable: int


class SqsPublisher:
    """The dispatcher's publisher, one message per unit."""

    def __init__(self, client: Any, queue_url: str) -> None:
        self._client = client
        self._queue_url = queue_url
        self._sent: set[str] = set()

    def publish(self, unit: WorkUnit) -> bool:
        """Send the unit, or return False for one this dispatch has already sent."""
        if unit.dedup_key in self._sent:
            return False
        self._client.send_message(QueueUrl=self._queue_url, MessageBody=encode(unit))
        self._sent.add(unit.dedup_key)
        return True


class SqsConsumer:
    """The worker's side of the queue: receive a batch, delete what was settled."""

    def __init__(
        self,
        client: Any,
        queue_url: str,
        *,
        wait_seconds: int = LONG_POLL_SECONDS,
        logger: logging.Logger = LOGGER,
    ) -> None:
        self._client = client
        self._queue_url = queue_url
        self._wait = wait_seconds
        self._log = logger

    def receive(self, max_messages: int = BATCH) -> Received:
        """One long poll. A message that cannot be decoded is logged and left on the queue."""
        response = self._client.receive_message(
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=min(max_messages, BATCH),
            WaitTimeSeconds=self._wait,
            MessageSystemAttributeNames=["ApproximateReceiveCount"],
        )
        deliveries: list[Delivery] = []
        undecodable = 0
        for message in response.get("Messages", ()):
            attempt = int(message.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
            try:
                unit = decode(message["Body"])
            except UndecodableMessageError as failure:
                undecodable += 1
                self._log.error(
                    "a message could not be decoded and is left for the redrive",
                    extra={
                        "message_id": message.get("MessageId"),
                        "receive_count": attempt,
                        "reason": str(failure),
                    },
                )
                continue
            deliveries.append(
                Delivery(
                    unit=unit,
                    receipt=message["ReceiptHandle"],
                    attempt=attempt,
                    message_id=message["MessageId"],
                )
            )
        return Received(deliveries=tuple(deliveries), undecodable=undecodable)

    def delete(self, deliveries: Iterable[Delivery]) -> tuple[str, ...]:
        """Delete each delivery. Returns the ids SQS refused, each logged.

        A refused delete is not lost work: the unit is delivered again, and the ledger's claim
        on its dedup key makes the second run a skip.
        """
        pending = list(deliveries)
        refused: list[str] = []
        for start in range(0, len(pending), BATCH):
            chunk = pending[start : start + BATCH]
            response = self._client.delete_message_batch(
                QueueUrl=self._queue_url,
                Entries=[
                    {"Id": str(index), "ReceiptHandle": one.receipt}
                    for index, one in enumerate(chunk)
                ],
            )
            for entry in response.get("Failed", ()):
                delivery = chunk[int(entry["Id"])]
                refused.append(delivery.message_id)
                self._log.warning(
                    "a delete was refused, so the unit will be delivered again",
                    extra={"message_id": delivery.message_id, "code": entry.get("Code")},
                )
        return tuple(refused)
