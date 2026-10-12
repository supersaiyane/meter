"""Bedrock usage per caller, from the invocation logs, read as aggregates and never as bodies.

P13 spec section 5.4, TASK-P13-003, FEAT-082, OPEN-32. An account that turns on Bedrock's model
invocation logging and sends it to CloudWatch Logs gets one event per call, naming the caller's
ARN, the model, the token counts and whatever key value pairs the caller attached, its
`requestMetadata`. The same event holds the prompt and the response. So this reads the logs only
through one CloudWatch Logs Insights `stats` query per day: every value it returns is a count or
a sum, grouped by caller, model and, when a deployment names one, an application key. Nothing a
caller sent a model reaches Meter, and `tests/providers/aws/test_bedrock_invocations.py` fails the
gate if the query ever names a body or returns anything but an aggregate.

**Where the logs do not go to CloudWatch Logs, the account is NotOptedIn**, with the step that
turns it on. Logs delivered only to S3 read the same, because Meter reads CloudWatch Logs.

Like every adapter here this has made no real call, ISS-002. The field names are the ones AWS
documents for the invocation log schema, read on 2026-10-12.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from finops_core.config import Settings
from finops_core.domain.account import AccountKey
from finops_core.domain.ai import AiUsage
from finops_core.errors import (
    AccessDenied,
    CollectionError,
    Misconfigured,
    NotOptedIn,
    SchemaDrift,
    Throttled,
)
from finops_providers.aws.client import botocore_config, error_code, translate

COLLECTOR = "bedrock_invocations"
#: The source, as `ai_usage_daily` names it.
BEDROCK = "bedrock"

#: The longest one day's query may run before it is stopped and the unit fails Throttled. Logs
#: Insights runs a query for up to 60 minutes; a day of one account's aggregates is seconds.
QUERY_TIMEOUT_SECONDS: Final = 300.0  # allow-hardcoded: a bound on our own wait, not an AWS limit
POLL_SECONDS: Final = 2.0  # allow-hardcoded: how often our own wait asks, not an AWS limit

#: A request metadata key Meter will put in a query. Bedrock's own limit for a key is 256
#: characters; this is narrower on purpose, because the key is written into query text.
METADATA_KEY: Final = re.compile(r"[A-Za-z0-9_-]{1,64}")

#: The fields of the invocation log the query reads, every one a count or an identifier.
CALLER: Final = "identity.arn"
MODEL: Final = "modelId"
#: The names the query gives its aggregates, and the only values it returns besides the groups.
SUMS: Final[dict[str, str]] = {
    "input_tokens": "input.inputTokenCount",
    "output_tokens": "output.outputTokenCount",
    "cache_read_tokens": "input.cacheReadInputTokenCount",
    "cache_write_tokens": "input.cacheWriteInputTokenCount",
}

#: Logs Insights answers LimitExceededException when the account already runs as many queries
#: as it may, which is a request to wait rather than a fault.
_BUSY: Final = frozenset({"LimitExceededException"})

ClientFactory = Callable[[str, str], Any]


def aggregate_query(metadata_key: str = "") -> str:
    """The one query this adapter runs. Every output is a count, a sum or a group.

    `metadata_key` names the request metadata key a deployment's applications name themselves
    under, and the query groups by its value; empty, and it does not.
    """
    groups = [CALLER, MODEL]
    if metadata_key:
        groups.append(f"requestMetadata.{metadata_key}")
    sums = ", ".join(f"sum({field}) as {name}" for name, field in SUMS.items())
    return f"filter ispresent({MODEL}) | stats count(*) as requests, {sums} by {', '.join(groups)}"


class BedrockInvocationLogs:
    """`InvocationLogs` over CloudWatch Logs Insights, in one member account's session."""

    def __init__(
        self,
        settings: Settings,
        tenant_id: Any,
        *,
        session: Any = None,
        client_factory: ClientFactory | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._tenant_id = tenant_id
        self._session = session
        self._factory = client_factory or self._default_client
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleeper = sleeper
        self._monotonic = monotonic

    def _default_client(self, service: str, region: str) -> Any:
        maker = self._session or boto3
        return maker.client(service, region_name=region, config=botocore_config(self._settings))

    # -- the port ----------------------------------------------------------

    def usage(
        self, account: AccountKey, region: str, start: datetime, end: datetime
    ) -> Iterable[AiUsage]:
        scope = f"{account}:{region}"
        key = self._settings.ai_request_metadata_key
        if key and not METADATA_KEY.fullmatch(key):
            raise Misconfigured(
                scope_key=scope,
                collector=COLLECTOR,
                detail="METER_AI_REQUEST_METADATA_KEY is not a request metadata key: "
                "letters, digits, hyphens and underscores, at most 64",
            )
        group = self._log_group(scope, region)
        logs = self._factory("logs", region)
        rows: list[AiUsage] = []
        for day_start, day_end in _days(start, end):
            results = self._run(logs, scope, group, day_start, day_end, aggregate_query(key))
            rows.extend(self._row(account, region, day_start, day_end, scope, r) for r in results)
        return tuple(rows)

    # -- reading -----------------------------------------------------------

    def _log_group(self, scope: str, region: str) -> str:
        """The CloudWatch Logs group the account's invocation logging writes to, or NotOptedIn."""
        try:
            config = self._factory("bedrock", region).get_model_invocation_logging_configuration()
        except (ClientError, BotoCoreError) as error:
            raise translate(error, scope, COLLECTOR) from error
        logging = config.get("loggingConfig") or {}
        group = (logging.get("cloudWatchConfig") or {}).get("logGroupName")
        if group:
            return str(group)
        where = "to S3 only" if logging.get("s3Config") else "nowhere"
        raise NotOptedIn(
            scope_key=scope,
            collector=COLLECTOR,
            detail=f"Bedrock model invocation logging in this account and Region writes {where}, "
            "so who called which model cannot be read. Turn on invocation logging to a "
            "CloudWatch Logs group matching the StackSet parameter InvocationLogGroupPattern",
        )

    def _run(
        self, logs: Any, scope: str, group: str, start: datetime, end: datetime, query: str
    ) -> list[list[dict[str, str]]]:
        try:
            started = logs.start_query(
                logGroupName=group,
                startTime=int(start.timestamp()),
                # Logs Insights' end is inclusive, to the second; the window here is half open.
                endTime=int(end.timestamp()) - 1,
                queryString=query,
            )
        except ClientError as error:
            raise self._typed(error, scope, group) from error
        except BotoCoreError as error:
            raise translate(error, scope, COLLECTOR) from error
        query_id = started["queryId"]
        deadline = self._monotonic() + QUERY_TIMEOUT_SECONDS
        while True:
            try:
                answer = logs.get_query_results(queryId=query_id)
            except (ClientError, BotoCoreError) as error:
                raise translate(error, scope, COLLECTOR) from error
            status = answer.get("status")
            if status == "Complete":
                return self._every_page(logs, scope, query_id, answer)
            if status in ("Failed", "Cancelled", "Timeout", "Unknown"):
                raise Throttled(
                    scope_key=scope,
                    collector=COLLECTOR,
                    detail=f"the Logs Insights query on {group} ended {status}; the next run asks "
                    "again",
                )
            if self._monotonic() >= deadline:
                # Not stopped: stopping a query is an action the read only role is not granted,
                # and Logs Insights ends a query on its own within the hour.
                raise Throttled(
                    scope_key=scope,
                    collector=COLLECTOR,
                    detail=f"the Logs Insights query on {group} had not finished after "
                    f"{QUERY_TIMEOUT_SECONDS:.0f} seconds; the next run asks again",
                )
            self._sleeper(POLL_SECONDS)

    def _every_page(
        self, logs: Any, scope: str, query_id: str, answer: dict[str, Any]
    ) -> list[list[dict[str, str]]]:
        """Every result of a complete query. Logs Insights pages a large answer by `nextToken`,
        which botocore declares no paginator for, so the pages are followed here."""
        results = list(answer.get("results") or [])
        token = answer.get("nextToken")
        while token:
            try:
                page = logs.get_query_results(queryId=query_id, nextToken=token)
            except (ClientError, BotoCoreError) as error:
                raise translate(error, scope, COLLECTOR) from error
            results.extend(page.get("results") or [])
            token = page.get("nextToken")
        return results

    def _typed(self, error: ClientError, scope: str, group: str) -> CollectionError:
        code = error_code(error)
        if code in _BUSY:
            return Throttled(
                scope_key=scope,
                collector=COLLECTOR,
                detail=f"{code}: the account is running as many Logs Insights queries as it may",
            )
        if code == "ResourceNotFoundException":
            return Misconfigured(
                scope_key=scope,
                collector=COLLECTOR,
                detail=f"the invocation logging configuration names {group}, which does not exist",
            )
        typed = translate(error, scope, COLLECTOR)
        if isinstance(typed, AccessDenied):
            return AccessDenied(
                scope_key=scope,
                collector=COLLECTOR,
                detail=f"{typed.detail}. The collector role may start a query only on log groups "
                "matching the StackSet parameter InvocationLogGroupPattern",
            )
        return typed

    # -- mapping -----------------------------------------------------------

    def _row(
        self,
        account: AccountKey,
        region: str,
        start: datetime,
        end: datetime,
        scope: str,
        result: list[dict[str, str]],
    ) -> AiUsage:
        cells = {cell.get("field", ""): cell.get("value") for cell in result}
        model = cells.get(MODEL)
        if not model or "requests" not in cells:
            raise SchemaDrift(
                scope_key=scope,
                collector=COLLECTOR,
                detail="a Logs Insights result lacked the model or the request count it groups by",
            )
        key = self._settings.ai_request_metadata_key
        application = cells.get(f"requestMetadata.{key}") if key else None
        return AiUsage(
            tenant_id=self._tenant_id,
            provider=BEDROCK,
            account_id=account.account_id,
            usage_date=start.date(),
            model=str(model),
            workspace=region,
            caller=str(cells.get(CALLER) or ""),
            application=str(application or ""),
            requests=_count(cells.get("requests"), scope),
            input_tokens=_count(cells.get("input_tokens"), scope),
            output_tokens=_count(cells.get("output_tokens"), scope),
            cache_read_tokens=_count(cells.get("cache_read_tokens"), scope),
            cache_write_tokens=_count(cells.get("cache_write_tokens"), scope),
            as_of=end,
            collected_at=max(self._clock(), end),
        )


def _days(start: datetime, end: datetime) -> Iterator[tuple[datetime, datetime]]:
    """Each UTC day in `[start, end)`, so every row is one day's, whatever the window."""
    day = start.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    while day < end:
        yield max(day, start), min(day + timedelta(days=1), end)
        day += timedelta(days=1)


def _count(raw: str | None, scope: str) -> int:
    """A count or a sum from a result. Absent is none counted: a model with no cache, no cache."""
    if raw is None or raw == "":
        return 0
    try:
        value = float(raw)
    except ValueError as error:
        raise SchemaDrift(
            scope_key=scope, collector=COLLECTOR, detail=f"{raw!r} is not a count"
        ) from error
    if value < 0 or value != int(value):
        raise SchemaDrift(scope_key=scope, collector=COLLECTOR, detail=f"{raw!r} is not a count")
    return int(value)
