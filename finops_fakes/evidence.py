"""Executions in memory, so a test can say what an account did.

The same idea as `FakeQuerySurface`: the observations are data, and a failure is
asked for rather than mocked.

One thing here is deliberately awkward, because the real thing is. The bundle is
keyed on the **normalised** query text, not on a fingerprint, because that is
what `finops_query.ownership.match_observed` matches on: CloudTrail records the
query a caller sent, and a templated panel stores `$region` while its executions
carry `eu-west-1`. Keying this on anything tidier would make the fake agree with
a matcher that does not exist.

The estate also has a past. `days_ago` reports the same queries run fewer times,
because an estate that did exactly the same thing every day draws a flat trend,
and a flat trend proves the plumbing and nothing else. The volume moves, the
collector does the arithmetic it always does, and the line rises because the
evidence changed rather than because the screen was told to draw a slope.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from finops_core.errors import CollectionError
from finops_core.ports.query import QueryParser

COLLECTOR = "query_evidence"

#: What the fake estate was seen doing. The key is the query as executed, which
#: for a templated panel is the resolved form: the panel stores a variable and
#: the account ran a value, and matching across that gap is the point of
#: `match_observed`.
DEFAULT_LOGS: Mapping[str, dict[str, Any]] = {
    "fields @timestamp, @message | filter @message like /ERROR/": {
        "runs": 2400,
        "bytes": 5_153_960_755_200.0,
        "runs_bytes": [2_147_483_648.0] * 2400,
        "log_groups": {"/aws/ecs/meter-api"},
    },
    # Two executions no panel and no alert rule claims, which is what makes
    # them ad hoc. FEAT-051. An estate without a pair like this cannot show the
    # feature at all, and cannot show the difference between a query somebody
    # owns and one nobody does.
    #
    # Somebody investigating an incident, reading a month of logs by hand. It
    # is not a mistake, it is expensive and recurring and on no dashboard.
    "fields @timestamp, @message | filter @message like /timeout/ | sort @timestamp desc": {
        "runs": 12,
        "bytes": 11_596_411_699_200.0,
        "runs_bytes": [966_367_641_600.0] * 12,
        "log_groups": {"/aws/ecs/meter-api", "/aws/rds/meter"},
        "principal": "bob@example.com",
    },
    # The same shape with nobody's name on it. CloudTrail did not say who ran
    # this, and the row is still reported: an expensive query nobody owns is
    # the case the feature exists for, so dropping it would remove the only
    # evidence that it happens.
    # The 500 below is inside a query somebody typed, not a threshold this
    # code compares against.
    "stats count() by bin(5m) | filter status >= 500": {  # allow-hardcoded: query text
        "runs": 45,
        "bytes": 966_367_641_600.0,
        "runs_bytes": [21_474_836_480.0] * 45,
        "log_groups": {"/aws/ecs/meter-api"},
        "principal": None,
    },
}

#: GetMetricData calls, by namespace and metric. Empty by default: the fake
#: estate holds no metric panel, and inventing one would make every test that
#: touches metrics agree with a fixture rather than with the code.
DEFAULT_METRICS: Mapping[str, int] = {}

DEFAULT_LOOKBACK_DAYS = 30

#: How much busier the fake estate is on a day than it was the day before. Four
#: percent compounding, which across a week is a rise a reader can see and
#: across a month is not an absurd claim about an estate that is growing.
DAILY_GROWTH = 1.04


def _fewer_runs(record: dict[str, Any], days_ago: int) -> dict[str, Any]:
    """The same query as the estate ran it `days_ago` days ago.

    Fewer runs, each scanning what it scans. The volume moves because the query
    was run less often and not because one run got hungrier, which is what keeps
    the cost per run steady across the history and leaves the run count carrying
    the trend on its own.

    A count that rounds below one means the query did not run that day. Nothing
    fills that in: `query_adhoc` refuses a row claiming zero runs, and a
    definition nobody executed falls back to its modelled figure. Both are true
    statements about a day with no executions, and inventing a run to keep the
    line unbroken would be the screen deciding what the estate did.
    """
    if days_ago <= 0:
        return record
    runs = round(record["runs"] * DAILY_GROWTH**-days_ago)
    per_run = tuple(record.get("runs_bytes") or ())
    if not per_run:
        share = runs / record["runs"] if record["runs"] else 0.0
        return {**record, "runs": runs, "bytes": record.get("bytes", 0.0) * share}
    # Cycled rather than truncated, so a record whose runs differ in size keeps
    # its mix of sizes instead of keeping only the first few.
    scaled = [per_run[index % len(per_run)] for index in range(runs)]
    return {**record, "runs": runs, "runs_bytes": scaled, "bytes": sum(scaled)}


class FakeQueryEvidence:
    """`QueryEvidence` in memory, with a configurable failure and a past."""

    def __init__(
        self,
        parser: QueryParser,
        logs: Mapping[str, dict[str, Any]] | None = None,
        metrics: Mapping[str, int] | None = None,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        principal: str | None = "alice@example.com",
        failure: type[CollectionError] | None = None,
        days_ago: int = 0,
    ) -> None:
        self._parser = parser
        self._logs = dict(DEFAULT_LOGS if logs is None else logs)
        self._metrics = dict(DEFAULT_METRICS if metrics is None else metrics)
        self._lookback_days = lookback_days
        self._principal = principal
        self._failure = failure
        # How far back this observation sits. Zero is the newest day and reports
        # the records as written, so a single day estate and every existing
        # fixture see exactly the numbers they saw before this existed.
        self._days_ago = days_ago

    def observations(
        self, *, account_id: str, region: str, lookback_days: int
    ) -> Mapping[str, Any]:
        if self._failure is not None:
            raise self._failure(
                scope_key=f"aws:{account_id}:{region}",
                collector=COLLECTOR,
                detail="planned by the fake evidence source",
            )
        # Normalised on the way out, because that is the key `match_observed`
        # looks up. Doing it here rather than in every fixture keeps the fixtures
        # readable as the queries they represent.
        logs = {
            self._parser.normalise(query): _fewer_runs(record, self._days_ago)
            for query, record in self._logs.items()
        }
        # A record may name its own caller, and may name it as absent. Falling
        # back to the constructor's principal keeps every existing fixture
        # behaving as it did, while letting one execution be unattributed on
        # purpose rather than by omission.
        principals: dict[str, str] = {}
        for query, record in self._logs.items():
            who = record.get("principal", self._principal)
            if who:
                principals[self._parser.normalise(query)] = who

        return {
            "logs": logs,
            "principal_by_query": principals,
            "gmd_by_metric": dict(self._metrics),
            # The window actually covered, which a caller must use rather than
            # the one it asked for.
            "lookback_days": min(lookback_days, self._lookback_days),
        }
