"""The AMG connection strategy.

`moto` implements no Grafana operations at all: `ListWorkspaces`,
`DescribeWorkspace`, `CreateWorkspace` and every service account call answer
"Not yet implemented". The plan asked for the contract suite under moto and that
is not available, recorded as ISS-141.

What replaces it is stronger for the thing that matters here. `botocore.stub`
validates a request and a response against the real service model, so a wrong
parameter name or a missing response field fails, which is precisely the class
of mistake an adapter makes. Behaviour around the call, the token loan and its
revocation, is asserted against a recording fake.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber

from finops_core.domain.query import (
    ControlAction,
    ControlRequest,
    QueryOrigin,
    SurfaceKind,
)
from finops_core.errors import AccessDenied, CollectionError
from finops_core.ports.query import QuerySurface
from finops_providers.grafana.amg import AmgQuerySurface, Scope
from finops_query.parser import GrafanaQueryParser

NOW = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)
SCOPES = (Scope(account_id="111122223333", region="eu-west-2"),)


def workspace(ws_id: str = "g-1", status: str = "ACTIVE") -> dict[str, Any]:
    """A workspace shaped the way AWS actually returns one.

    The four fields below the endpoint are required by the service model and
    were missing from the first draft of this helper. The Stubber caught it;
    moto could not have, because it implements none of this API.
    """
    return {
        "id": ws_id,
        "name": f"name-{ws_id}",
        "status": status,
        "endpoint": f"{ws_id}.grafana-workspace.eu-west-2.amazonaws.com",
        "created": NOW,
        "modified": NOW,
        "grafanaVersion": "10.4",
        "authentication": {"providers": ["AWS_SSO"]},
    }


class RecordingGrafana:
    """A boto3 grafana client that records what it was asked to do."""

    def __init__(
        self,
        pages: list[dict[str, Any]] | None = None,
        fail_list: Exception | None = None,
        fail_token: Exception | None = None,
    ) -> None:
        self.pages = pages if pages is not None else [{"workspaces": [workspace()]}]
        self.fail_list = fail_list
        self.fail_token = fail_token
        self.calls: list[str] = []

    def list_workspaces(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("list_workspaces")
        if self.fail_list is not None:
            raise self.fail_list
        index = 1 if kwargs.get("nextToken") else 0
        return self.pages[index]

    def create_workspace_service_account(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("create_workspace_service_account")
        return {"id": "sa-1", "name": kwargs["name"], "grafanaRole": kwargs["grafanaRole"]}

    def create_workspace_service_account_token(self, **_: Any) -> dict[str, Any]:
        self.calls.append("create_workspace_service_account_token")
        if self.fail_token is not None:
            raise self.fail_token
        return {"serviceAccountToken": {"id": "tok-1", "key": "a-token"}}

    def delete_workspace_service_account_token(self, **_: Any) -> dict[str, Any]:
        self.calls.append("delete_workspace_service_account_token")
        return {}

    def delete_workspace_service_account(self, **_: Any) -> dict[str, Any]:
        self.calls.append("delete_workspace_service_account")
        return {}


class RecordingSecrets:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_secret_value(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs["SecretId"])
        return {"SecretString": "a-configured-token"}


class FakeTransport:
    """Stands in for GrafanaClient, so the HTTP layer is not retested here."""

    def __init__(self, dashboards: Any = (), body: Any = None, rules: Any = ()) -> None:
        self.dashboards = dashboards
        self.body = body or {}
        self.rules = rules
        self.closed = False

    def search_dashboards(self) -> Any:
        return self.dashboards

    def dashboard(self, _uid: str) -> Any:
        return self.body

    def alert_rules(self) -> Any:
        return self.rules

    def close(self) -> None:
        self.closed = True


def surface_with(
    grafana: RecordingGrafana,
    secrets: RecordingSecrets | None = None,
    transport: FakeTransport | None = None,
    secret_names: dict[str, str] | None = None,
    scopes: tuple[Scope, ...] = SCOPES,
) -> AmgQuerySurface:
    def factory(service: str, _scope: Scope) -> Any:
        return secrets if service == "secretsmanager" else grafana

    return AmgQuerySurface(
        scopes=scopes,
        client_factory=factory,
        parser=GrafanaQueryParser(),
        now=lambda: NOW,
        http_timeout_seconds=5.0,
        token_ttl_seconds=900,
        secret_names=secret_names,
        transport_factory=(lambda _ws, _token: transport) if transport else None,
    )


def test_it_satisfies_the_port() -> None:
    assert isinstance(surface_with(RecordingGrafana()), QuerySurface)


def test_discovery_reads_every_page() -> None:
    grafana = RecordingGrafana(
        pages=[
            {"workspaces": [workspace("g-1")], "nextToken": "more"},
            {"workspaces": [workspace("g-2")]},
        ]
    )
    found = list(surface_with(grafana).discover())
    assert [i.surface_id for i in found] == ["g-1", "g-2"]
    assert grafana.calls.count("list_workspaces") == 2


def test_a_workspace_carries_the_account_and_region_it_was_listed_in() -> None:
    """Otherwise the account has to be guessed downstream, and it was: the
    collector parsed an identifier and fell back to the workspace id, so the
    column scope enforcement reads held a workspace id. ISS-153."""
    found = list(
        surface_with(RecordingGrafana(pages=[{"workspaces": [workspace("g-1")]}])).discover()
    )
    assert [(i.account_id, i.region_id) for i in found] == [("111122223333", "eu-west-2")]


def test_a_region_that_cannot_be_listed_becomes_a_visible_instance() -> None:
    # A silently shorter estate is the failure this product exists to prevent,
    # and nothing downstream could tell the region was meant to be there.
    failure = ClientError({"Error": {"Code": "AccessDeniedException"}}, "ListWorkspaces")
    two = (*SCOPES, Scope(account_id="444455556666", region="eu-west-1"))

    def factory(_service: str, scope: Scope) -> Any:
        return (
            RecordingGrafana()
            if scope.region == "eu-west-2"
            else RecordingGrafana(fail_list=failure)
        )

    surface = AmgQuerySurface(
        scopes=two,
        client_factory=factory,
        parser=GrafanaQueryParser(),
        now=lambda: NOW,
        http_timeout_seconds=5.0,
        token_ttl_seconds=900,
    )
    found = list(surface.discover())
    unreachable = [i for i in found if not i.reachable]
    assert len(unreachable) == 1
    assert unreachable[0].surface_id == "aws:444455556666:eu-west-1"
    assert unreachable[0].unreachable_cause


def test_discovery_raises_only_when_nothing_could_be_enumerated() -> None:
    failure = ClientError({"Error": {"Code": "AccessDeniedException"}}, "ListWorkspaces")
    surface = surface_with(RecordingGrafana(fail_list=failure))
    with pytest.raises(CollectionError):
        list(surface.discover())


def test_a_workspace_that_is_not_active_is_listed_and_marked() -> None:
    grafana = RecordingGrafana(pages=[{"workspaces": [workspace("g-9", status="CREATING")]}])
    found = list(surface_with(grafana).discover())
    assert found[0].reachable is False
    assert found[0].kind is SurfaceKind.MANAGED_GRAFANA


def test_a_token_is_minted_and_revoked_around_a_read() -> None:
    grafana = RecordingGrafana()
    surface = surface_with(grafana, transport=FakeTransport())
    instance = next(iter(surface.discover()))
    list(surface.list_queries(instance))
    assert grafana.calls == [
        "list_workspaces",
        "create_workspace_service_account",
        "create_workspace_service_account_token",
        "delete_workspace_service_account_token",
        "delete_workspace_service_account",
    ]


def test_the_service_account_is_revoked_even_when_the_read_fails() -> None:
    # The prototype left credentials behind when a run died half way. Minting is
    # a loan, not an allocation.
    class Exploding(FakeTransport):
        def search_dashboards(self) -> Any:
            raise RuntimeError("the read blew up")

    grafana = RecordingGrafana()
    surface = surface_with(grafana, transport=Exploding())
    instance = next(iter(surface.discover()))
    with pytest.raises(RuntimeError):
        list(surface.list_queries(instance))
    assert "delete_workspace_service_account" in grafana.calls


def test_the_service_account_is_revoked_when_the_token_call_fails() -> None:
    failure = ClientError({"Error": {"Code": "ThrottlingException"}}, "CreateToken")
    grafana = RecordingGrafana(fail_token=failure)
    surface = surface_with(grafana, transport=FakeTransport())
    instance = next(iter(surface.discover()))
    with pytest.raises(CollectionError):
        list(surface.list_queries(instance))
    assert "delete_workspace_service_account" in grafana.calls


def test_a_configured_secret_is_used_instead_of_minting() -> None:
    grafana = RecordingGrafana()
    secrets = RecordingSecrets()
    surface = surface_with(
        grafana,
        secrets=secrets,
        transport=FakeTransport(),
        secret_names={"g-1": "meter/grafana/g-1"},
    )
    instance = next(iter(surface.discover()))
    list(surface.list_queries(instance))
    assert secrets.calls == ["meter/grafana/g-1"]
    assert "create_workspace_service_account" not in grafana.calls


def test_an_unreachable_instance_is_not_read() -> None:
    grafana = RecordingGrafana(pages=[{"workspaces": [workspace("g-9", status="CREATING")]}])
    surface = surface_with(grafana, transport=FakeTransport())
    instance = next(iter(surface.discover()))
    with pytest.raises(AccessDenied):
        list(surface.list_queries(instance))


def test_v1_writes_nothing_and_says_so_rather_than_raising() -> None:
    # Architectural constraint 6. A normal answer, so the caller tries a
    # different control instead of abandoning the run.
    surface = surface_with(RecordingGrafana())
    instance = next(iter(surface.discover()))
    outcome = surface.apply_control(
        instance, ControlRequest(fingerprint="fp", action=ControlAction.THROTTLE)
    )
    assert outcome.applied is False
    assert "read only" in outcome.detail


def test_the_list_workspaces_call_matches_the_real_service_model() -> None:
    # What moto would have given us. The Stubber validates the response against
    # botocore's own model, so a field this adapter reads but AWS does not
    # return fails here rather than in production.
    client = boto3.client(
        "grafana",
        region_name="eu-west-2",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )
    stub = Stubber(client)
    stub.add_response("list_workspaces", {"workspaces": [workspace("g-real")]}, {})
    stub.activate()

    surface = AmgQuerySurface(
        scopes=SCOPES,
        client_factory=lambda _service, _scope: client,
        parser=GrafanaQueryParser(),
        now=lambda: NOW,
        http_timeout_seconds=5.0,
        token_ttl_seconds=900,
    )
    found = list(surface.discover())
    stub.deactivate()

    assert [i.surface_id for i in found] == ["g-real"]
    assert found[0].location.endswith("amazonaws.com")


PANEL_BODY = {
    "dashboard": {
        "title": "Platform overview",
        "refresh": "10s",
        "time": {"from": "now-30d"},
        "panels": [
            {
                "title": "Error rate by service",
                "datasource": {"type": "prometheus"},
                "targets": [{"refId": "A", "expr": "sum(rate(errors_total[5m]))"}],
            }
        ],
    }
}

ALERT_RULES = (
    {
        "uid": "rule-1",
        "title": "Error budget burn",
        "ruleGroup": "slo",
        "intervalSeconds": 60,
        "data": [
            {
                "refId": "A",
                "model": {
                    "datasource": {"type": "prometheus"},
                    "expr": "sum(rate(errors_total[1m]))",
                },
            }
        ],
    },
)


def read_definitions() -> list[Any]:
    transport = FakeTransport(dashboards=({"uid": "abc123"},), body=PANEL_BODY, rules=ALERT_RULES)
    surface = surface_with(RecordingGrafana(), transport=transport)
    instance = next(iter(surface.discover()))
    return list(surface.list_queries(instance))


def test_a_panel_and_an_alert_both_become_definitions() -> None:
    found = read_definitions()
    assert {d.origin for d in found} == {QueryOrigin.PANEL, QueryOrigin.ALERT}


def test_an_alert_carries_its_own_interval_not_the_dashboard_refresh() -> None:
    # An alert runs whether anybody is watching or not, and conflating the two
    # understates it by orders of magnitude.
    alert = next(d for d in read_definitions() if d.origin is QueryOrigin.ALERT)
    panel = next(d for d in read_definitions() if d.origin is QueryOrigin.PANEL)
    assert alert.refresh_seconds == 60
    assert panel.refresh_seconds == 10
    assert panel.window_seconds == 30 * 86400


def test_every_definition_is_fingerprinted_and_attributed_to_its_container() -> None:
    for definition in read_definitions():
        assert definition.fingerprint
        assert definition.surface_id == "g-1"
        assert definition.engine != "unknown"


def test_the_transport_is_closed_after_a_read() -> None:
    transport = FakeTransport(dashboards=({"uid": "abc123"},), body=PANEL_BODY)
    surface = surface_with(RecordingGrafana(), transport=transport)
    instance = next(iter(surface.discover()))
    list(surface.list_queries(instance))
    assert transport.closed is True
