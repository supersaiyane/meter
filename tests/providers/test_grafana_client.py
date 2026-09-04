"""The Grafana reader, and the failure it refuses to hide.

The prototype wrapped every call in `except Exception: return []`, so a
workspace the token could not read reported zero dashboards. That renders as
"this workspace costs nothing" rather than as "we could not look", and it is
constraint 5 exactly. Most of this file exists to hold that closed.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from finops_core.errors import (
    AccessDenied,
    CollectionError,
    NotOptedIn,
    SchemaDrift,
    Throttled,
    Unreachable,
)
from finops_providers.grafana.client import (
    SEARCH_LIMIT,
    GrafanaClient,
    Workspace,
    endpoint_from_url,
)

WORKSPACE = Workspace(id="g-abc123", name="observability", endpoint="g-abc123.example.invalid")


def client_returning(payload: Any, status: int = 200) -> GrafanaClient:
    """A client whose transport answers with one fixed response."""

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        return httpx.Response(status, json=payload)

    transport = httpx.Client(base_url="https://x.invalid", transport=httpx.MockTransport(handler))
    return GrafanaClient(WORKSPACE, "token", 5.0, transport=transport)


def client_raising(error: Exception) -> GrafanaClient:
    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001
        raise error

    transport = httpx.Client(base_url="https://x.invalid", transport=httpx.MockTransport(handler))
    return GrafanaClient(WORKSPACE, "token", 5.0, transport=transport)


@pytest.mark.parametrize(
    ("status", "cause"),
    [
        (401, AccessDenied),
        (403, AccessDenied),
        (404, NotOptedIn),
        (429, Throttled),
        (500, SchemaDrift),
        (503, Unreachable),
    ],
)
def test_every_http_failure_becomes_a_typed_cause(
    status: int, cause: type[CollectionError]
) -> None:
    """Never an empty list. A workspace that could not be read must not report
    zero dashboards, because zero is a number and the reader will believe it."""
    with pytest.raises(cause):
        client_returning({"message": "nope"}, status=status).search_dashboards()


def test_an_unknown_status_is_not_reported_as_no_data() -> None:
    """SchemaDrift rather than NoData, for the same reason the AWS adapter does
    it: an unknown failure rendered as a zero is the defect the taxonomy exists
    to prevent."""
    with pytest.raises(SchemaDrift):
        client_returning({}, status=418).search_dashboards()


def test_a_timeout_is_unreachable_rather_than_unknown() -> None:
    with pytest.raises(Unreachable):
        client_raising(httpx.ConnectTimeout("slow")).search_dashboards()


def test_a_connection_failure_is_unreachable() -> None:
    with pytest.raises(Unreachable):
        client_raising(httpx.ConnectError("refused")).alert_rules()


def test_a_failure_names_the_workspace_it_happened_to() -> None:
    """A typed cause with no scope is a failure nobody can act on."""
    with pytest.raises(AccessDenied) as raised:
        client_returning({}, status=403).search_dashboards()

    assert raised.value.scope_key == "grafana:g-abc123"
    assert raised.value.collector == "query_audit"


def test_dashboards_are_returned_when_the_call_succeeds() -> None:
    found = client_returning([{"uid": "a"}, {"uid": "b"}]).search_dashboards()

    assert [d["uid"] for d in found] == ["a", "b"]


def test_a_result_at_the_search_cap_is_refused_rather_than_accepted() -> None:
    """Grafana does not say it truncated. Auditing an unknown fraction of an
    estate and calling it the estate is worse than refusing."""
    with pytest.raises(SchemaDrift) as raised:
        client_returning([{"uid": str(i)} for i in range(SEARCH_LIMIT)]).search_dashboards()

    assert "truncated" in raised.value.detail


def test_a_response_of_the_wrong_shape_is_drift_not_an_empty_answer() -> None:
    with pytest.raises(SchemaDrift):
        client_returning({"not": "a list"}).search_dashboards()
    with pytest.raises(SchemaDrift):
        client_returning(["not an object"]).dashboard("uid-1")


def test_alert_rules_are_returned_when_provisioning_is_available() -> None:
    found = client_returning([{"uid": "rule-1"}]).alert_rules()

    assert found[0]["uid"] == "rule-1"


def test_provisioning_being_unavailable_is_not_the_same_as_no_rules() -> None:
    """404 means the workspace has not enabled the API, which is a
    configuration state rather than an absence of alert rules."""
    with pytest.raises(NotOptedIn):
        client_returning({}, status=404).alert_rules()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://g-abc.example.invalid", "g-abc.example.invalid"),
        ("http://g-abc.example.invalid/", "g-abc.example.invalid"),
        ("g-abc.example.invalid", "g-abc.example.invalid"),
        ("  https://g-abc.example.invalid/path  ", "g-abc.example.invalid"),
        ("", None),
        ("   ", None),
    ],
)
def test_a_workspace_url_is_read_however_it_was_written(raw: str, expected: str | None) -> None:
    """Both forms are written in practice, and silently ignoring one produces a
    missing workspace nobody can explain."""
    assert endpoint_from_url(raw) == expected


def test_the_client_closes_its_transport() -> None:
    with client_returning([]) as client:
        assert client.search_dashboards() == ()
