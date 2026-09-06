"""What an account actually executed, read from CloudTrail and query history.

Three sources, because no single one answers the whole question.

**CloudTrail `StartQuery`** gives the run count. Every Logs Insights execution
appears, whoever started it, including the ones no dashboard accounts for.

**`logs:DescribeQueries` and `GetQueryResults`** give the bytes. CloudTrail
records that a query ran, never how much it scanned, and the scan volume is the
term the whole Logs Insights cost rests on. Query history holds it for a limited
window, so this is best effort by design: when it answers, the assumed ingestion
rate drops out of the figure entirely; when it does not, the runs are still real
and `measure_logs_query` says exactly that.

**CloudTrail `GetMetricData`** gives metric call counts, bucketed by namespace
and metric. It is the weakest of the three and is part of why ISS-093 exists,
because CloudTrail identifies those calls by account and region and never by the
panel that made them.

A window that returns nothing comes back as an absent key rather than a zero.
Absent means unobserved, and the caller leaves the finding modelled.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

from finops_core.errors import SchemaDrift
from finops_core.ports.query import QueryParser
from finops_providers.aws.client import translate

COLLECTOR = "query_evidence"

#: CloudTrail pages at fifty events and this walks every page. A cap here would
#: silently undercount a busy account, which is the one error this module cannot
#: afford: an undercounted run rate reads as a cheaper query.
LOOKUP_PAGE_SIZE = 50

#: How many finished queries to ask history for. `DescribeQueries` returns the
#: most recent first, and the ones that matter for cost are the ones that ran.
DESCRIBE_LIMIT = 1000

ClientFactory = Callable[[str, str, str], Any]


def _events(
    client: Any, event_name: str, start: datetime, end: datetime, scope: str
) -> Iterator[dict[str, Any]]:
    """Every CloudTrail event of one name in the window, following every page."""
    token: str | None = None
    while True:
        request: dict[str, Any] = {
            "LookupAttributes": [{"AttributeKey": "EventName", "AttributeValue": event_name}],
            "StartTime": start,
            "EndTime": end,
            "MaxResults": LOOKUP_PAGE_SIZE,
        }
        if token:
            request["NextToken"] = token
        try:
            page = client.lookup_events(**request)
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=scope, collector=COLLECTOR) from failure

        for event in page.get("Events", ()):
            raw = event.get("CloudTrailEvent")
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError as broken:
                # Drift, and loud rather than skipped: an event this cannot read
                # is a run it cannot count, and an undercount reads as cheaper.
                raise SchemaDrift(
                    scope_key=scope,
                    collector=COLLECTOR,
                    detail="a CloudTrail event was not valid JSON",
                ) from broken

        token = page.get("NextToken")
        if not token:
            return


def _log_groups(params: Mapping[str, Any]) -> tuple[str, ...]:
    """Log groups from a StartQuery call, in either shape the API accepts."""
    names = params.get("logGroupNames")
    if isinstance(names, list):
        return tuple(str(name) for name in names)
    single = params.get("logGroupName")
    return (str(single),) if single else ()


class CloudTrailQueryEvidence:
    """`QueryEvidence` over CloudTrail and CloudWatch Logs query history."""

    def __init__(
        self,
        *,
        client_factory: ClientFactory,
        parser: QueryParser,
        now: Callable[[], datetime] | None = None,
        read_bytes: bool = True,
    ) -> None:
        self._client = client_factory
        # Supplied from above, so this adapter never imports the analysis it feeds.
        self._parser = parser
        self._now = now or (lambda: datetime.now(UTC))
        # Reading bytes costs a GetQueryResults call per query. It is worth it,
        # because it is what removes the ingestion assumption from the figure,
        # but it is switchable for an account where that call volume matters.
        self._read_bytes = read_bytes
        self._principals: dict[str, str] = {}

    def observations(
        self, *, account_id: str, region: str, lookback_days: int
    ) -> Mapping[str, Any]:
        scope = f"aws:{account_id}:{region}"
        end = self._now()
        start = end - timedelta(days=lookback_days)

        logs = self._logs_runs(account_id, region, start, end, scope)
        if self._read_bytes and logs:
            self._add_bytes(account_id, region, logs, scope)

        return {
            "logs": logs,
            "gmd_by_metric": self._metric_calls(account_id, region, start, end, scope),
            "lookback_days": lookback_days,
            # Who was seen running each query. Kept beside the counts rather
            # than inside them, because `Observed.merge` only carries the four
            # fields the cost arithmetic needs and would drop this.
            "principal_by_query": self._principals,
        }

    # -- runs, from CloudTrail ---------------------------------------------

    def _logs_runs(
        self, account_id: str, region: str, start: datetime, end: datetime, scope: str
    ) -> dict[str, dict[str, Any]]:
        client = self._client("cloudtrail", account_id, region)
        found: dict[str, dict[str, Any]] = {}
        self._principals = {}
        for detail in _events(client, "StartQuery", start, end, scope):
            params = detail.get("requestParameters") or {}
            query = params.get("queryString")
            if not query:
                continue
            key = self._parser.normalise(query)
            record = found.setdefault(
                key, {"runs": 0, "bytes": 0.0, "runs_bytes": [], "log_groups": set()}
            )
            record["runs"] += 1
            for group in _log_groups(params):
                record["log_groups"].add(group)
            # First writer wins, so the earliest caller in the window is the one
            # reported. Any of them is a guess at ownership, and a stable guess
            # is at least arguable.
            who = self._parser.principal_from(detail)
            if who and key not in self._principals:
                self._principals[key] = who
        return found

    # -- bytes, from query history -----------------------------------------

    def _add_bytes(
        self, account_id: str, region: str, logs: dict[str, dict[str, Any]], scope: str
    ) -> None:
        """Attach scanned bytes where history still holds them.

        Best effort on purpose. History is a limited window, so a query that ran
        a thousand times may have statistics for a handful of them, and
        `measure_logs_query` averages what it is given. Failing the whole run
        because bytes were unavailable would throw away the run counts too.
        """
        client = self._client("logs", account_id, region)
        try:
            described = client.describe_queries(maxResults=DESCRIBE_LIMIT)
        except (ClientError, BotoCoreError) as failure:
            raise translate(failure, scope_key=scope, collector=COLLECTOR) from failure

        for entry in described.get("queries", ()):
            key = self._parser.normalise(entry.get("queryString"))
            record = logs.get(key)
            query_id = entry.get("queryId")
            if record is None or not query_id:
                continue
            try:
                result = client.get_query_results(queryId=query_id)
            except (ClientError, BotoCoreError):
                # One unreadable query does not cost us the rest of the window.
                continue
            scanned = (result.get("statistics") or {}).get("bytesScanned")
            if scanned:
                record["bytes"] += float(scanned)
                record["runs_bytes"].append(float(scanned))

    # -- metric calls, from CloudTrail -------------------------------------

    def _metric_calls(
        self, account_id: str, region: str, start: datetime, end: datetime, scope: str
    ) -> dict[str, int]:
        client = self._client("cloudtrail", account_id, region)
        counts: dict[str, int] = {}
        for detail in _events(client, "GetMetricData", start, end, scope):
            params = detail.get("requestParameters") or {}
            for query in params.get("metricDataQueries") or ():
                stat = (query.get("metricStat") or {}).get("metric") or {}
                namespace = (stat.get("namespace") or "").lower()
                metric = (stat.get("metricName") or "").lower()
                if not namespace:
                    continue
                bucket = f"{namespace}|{metric}"
                counts[bucket] = counts.get(bucket, 0) + 1
        return counts
