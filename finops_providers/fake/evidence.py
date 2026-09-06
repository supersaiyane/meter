"""Executions in memory, so a test can say what an account did.

The same idea as `FakeQuerySurface`: the observations are data, and a failure is
asked for rather than mocked.

One thing here is deliberately awkward, because the real thing is. The bundle is
keyed on the **normalised** query text, not on a fingerprint, because that is
what `finops_query.ownership.match_observed` matches on: CloudTrail records the
query a caller sent, and a templated panel stores `$region` while its executions
carry `eu-west-1`. Keying this on anything tidier would make the fake agree with
a matcher that does not exist.
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


class FakeQueryEvidence:
    """`QueryEvidence` in memory, with a configurable failure."""

    def __init__(
        self,
        parser: QueryParser,
        logs: Mapping[str, dict[str, Any]] | None = None,
        metrics: Mapping[str, int] | None = None,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
        principal: str | None = "alice@example.com",
        failure: type[CollectionError] | None = None,
    ) -> None:
        self._parser = parser
        self._logs = dict(DEFAULT_LOGS if logs is None else logs)
        self._metrics = dict(DEFAULT_METRICS if metrics is None else metrics)
        self._lookback_days = lookback_days
        self._principal = principal
        self._failure = failure

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
        logs = {self._parser.normalise(query): record for query, record in self._logs.items()}
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
