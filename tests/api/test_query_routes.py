"""The three query governance routes, and the four ways they could mislead.

Ordering, because a page sorted in Python orders the page rather than the
estate. Scope, because a route that forgot its dependency must still not read
another tenant's findings. The published rate, because arithmetic with a
constant hidden in the frontend cannot be checked by the person reading it. And
the instance count, because an unreachable workspace reporting nought queries
makes an estate look smaller than it is.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4, uuid5

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from finops_api.db import models
from finops_api.identity import SessionSigner
from finops_api.main import create_app
from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.identity import Entitlement, Principal
from finops_core.domain.tenant import Scope

NOW = datetime(2026, 8, 27, 6, 0, tzinfo=UTC)
SIGNING_KEY = "a-test-signing-key"
IN_SCOPE = "111122223333"
OUT_OF_SCOPE = "444455556666"

#: Rows outlive a test, so every key is derived from the tenant rather than
#: fixed. Two tests sharing a primary key fail on the second one for a reason
#: that has nothing to do with what either was asserting.
KEYS = UUID("5eeded00-0000-4000-8000-00000000000f")


def key(tenant: UUID, name: str) -> UUID:
    return uuid5(KEYS, f"{tenant}:{name}")


pytestmark = pytest.mark.integration


class StubEntitlements:
    def __init__(self, scope: Scope) -> None:
        self.scope = scope

    def resolve(self, principal: Principal) -> Entitlement:
        return Entitlement(principal=principal, scope=self.scope, as_of=NOW, collected_at=NOW)


def seed(engine: Engine, tenant: UUID) -> None:
    """Two instances in scope, one out, and two findings an order apart.

    The cheap finding is inserted first so an unordered read would return it
    first: the ordering assertion has to be able to fail.
    """
    with engine.begin() as connection:
        for name, account, reachable, reason in (
            ("reachable", IN_SCOPE, True, None),
            ("unreachable", IN_SCOPE, False, "the workspace returned 403"),
            ("elsewhere", OUT_OF_SCOPE, True, None),
            # Self hosted, so it belongs to no cloud account and the account
            # filter has nothing to match it against.
            ("self-hosted", None, True, None),
        ):
            instance_id = key(tenant, name)
            connection.execute(
                models.grafana_instance.insert().values(
                    instance_id=instance_id,
                    tenant_id=tenant,
                    kind="AMG" if account else "SELF_HOSTED",
                    name=f"workspace-{name}",
                    endpoint=f"https://g-{name}.grafana-workspace.local",
                    account_id=account,
                    region_id="eu-west-2" if account else None,
                    reachable=reachable,
                    unreachable_reason=reason,
                    as_of=NOW,
                    collected_at=NOW,
                )
            )

        for which, panel, text_, cost, provenance, runs in (
            ("cheap", "Invoice totals", "fields @timestamp | limit 20", "1.80", "measured", 24),
            (
                "expensive",
                "Error rate by service",
                "fields @timestamp, @message | filter @message like /ERROR/",
                "5184.00",
                "modelled",
                None,
            ),
        ):
            query_id = key(tenant, which)
            connection.execute(
                models.query_definition.insert().values(
                    query_id=query_id,
                    tenant_id=tenant,
                    instance_id=key(tenant, "reachable" if which == "cheap" else "elsewhere"),
                    origin="PANEL",
                    dashboard_uid="dash-1",
                    dashboard_title="Platform overview",
                    folder_uid="folder-1",
                    panel_id=panel,
                    ref_id="A",
                    engine="LOGS_INSIGHTS",
                    query_text=text_,
                    fingerprint=str(query_id),
                    query_key=str(query_id),
                    target={"targets": ["/aws/ecs/meter-api"], "region": "eu-west-2"},
                    refresh_seconds=10,
                    range_seconds=2_592_000,
                    last_editor="alice@example.local",
                    as_of=NOW,
                    collected_at=NOW,
                )
            )
            connection.execute(
                models.query_finding.insert().values(
                    finding_id=query_id,
                    tenant_id=tenant,
                    query_id=query_id,
                    run_date=NOW.date(),
                    runs_per_day=Decimal("8640.00"),
                    scan_bytes_per_run=4_294_967_296,
                    cost_month_usd=Decimal(cost),
                    provenance=provenance,
                    measured_runs=runs,
                    severity="high" if cost.startswith("5") else "low",
                    owner_email=None,
                    owner_source=None,
                    why="refreshes every 10 seconds over a 30 day window",
                    as_of=NOW,
                    collected_at=NOW,
                )
            )


def client_for(engine: Engine, scope: Scope, settings: Settings) -> tuple[TestClient, str]:
    signer = SessionSigner(SIGNING_KEY, ttl_hours=8, clock=lambda: NOW)
    app = create_app(
        engine=engine, entitlements=StubEntitlements(scope), signer=signer, settings=settings
    )
    return TestClient(app, raise_server_exceptions=False), signer.issue(
        "p2", "someone@example.local", scope
    )


def another_tenant(engine: Engine) -> UUID:
    """A real second tenant, not an invented id.

    An id with no tenant row behind it fails on the audit insert rather than on
    the read, which would prove the audit trail works and say nothing at all
    about scope.
    """
    new_id = uuid4()
    with engine.begin() as connection:
        connection.execute(models.tenant.insert().values(tenant_id=new_id, name=f"tenant-{new_id}"))
    return new_id


def narrow(tenant: UUID) -> Scope:
    return Scope(
        tenant_id=tenant,
        is_global=False,
        accounts=frozenset({AccountKey(provider=Provider.AWS, account_id=IN_SCOPE)}),
    )


def everything(tenant: UUID) -> Scope:
    """A viewer of the whole tenant, for the assertions about a finding whose
    workspace sits in the account the narrow scope excludes."""
    return Scope(tenant_id=tenant, is_global=True, accounts=frozenset())


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- findings ----------------------------------------------------------------


def test_findings_come_back_most_expensive_first(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    payload = client.get("/api/v1/query/findings", headers=auth(token)).json()
    costs = [row["monthly_cost"] for row in payload["data"]]
    assert costs == ["5184.0000000000", "1.8000000000"]


def test_a_modelled_finding_says_so_and_carries_no_measured_runs(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The distinction is the product. A modelled figure that reads as measured
    is worse than no figure, because a number on a page is believed."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    rows = client.get("/api/v1/query/findings", headers=auth(token)).json()["data"]
    modelled = next(row for row in rows if row["provenance"] == "modelled")
    assert modelled["measured_runs"] is None
    measured = next(row for row in rows if row["provenance"] == "measured")
    assert measured["measured_runs"] == 24


def test_an_unattributed_finding_sends_null_rather_than_a_word(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    # The screen decides what an absence reads as. The API does not put a word
    # in its mouth, because "unattributed" would then be untranslatable and
    # would sort among real addresses.
    seed(engine, tenant_id)
    client, token = client_for(engine, narrow(tenant_id), settings)
    rows = client.get("/api/v1/query/findings", headers=auth(token)).json()["data"]
    assert all(row["owner"] is None for row in rows)


def test_a_finding_from_an_out_of_scope_account_is_not_listed(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A finding carries no account of its own. Its account is the account of
    the workspace it was read from, and the scope has to reach that far or a
    viewer restricted to one account reads the whole tenant's queries."""
    seed(engine, tenant_id)
    client, token = client_for(engine, narrow(tenant_id), settings)
    rows = client.get("/api/v1/query/findings", headers=auth(token)).json()["data"]
    assert [row["panel_title"] for row in rows] == ["Invoice totals"]


def test_a_global_viewer_sees_the_finding_the_narrow_one_cannot(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    # The pair matters. Without this the test above would also pass if the
    # expensive finding had simply never been written.
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    rows = client.get("/api/v1/query/findings", headers=auth(token)).json()["data"]
    assert [row["panel_title"] for row in rows] == ["Error rate by service", "Invoice totals"]


def test_a_workspace_belonging_to_no_account_is_out_of_a_narrowed_scope(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A self hosted Grafana names no cloud account, so a caller restricted to
    two accounts has not been given it. A global viewer still sees it."""
    seed(engine, tenant_id)
    narrowed, token = client_for(engine, narrow(tenant_id), settings)
    names = [
        row["name"]
        for row in narrowed.get("/api/v1/query/instances", headers=auth(token)).json()["data"]
    ]
    assert "workspace-self-hosted" not in names

    unrestricted, other = client_for(engine, everything(tenant_id), settings)
    seen = [
        row["name"]
        for row in unrestricted.get("/api/v1/query/instances", headers=auth(other)).json()["data"]
    ]
    assert "workspace-self-hosted" in seen


def test_another_tenants_findings_are_not_visible(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, narrow(another_tenant(engine)), settings)
    assert client.get("/api/v1/query/findings", headers=auth(token)).json()["data"] == []


# --- one finding -------------------------------------------------------------


def test_the_detail_carries_the_published_rate(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Without it the working on the screen has a constant nobody can check."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    payload = client.get(
        f"/api/v1/query/findings/{key(tenant_id, 'expensive')}", headers=auth(token)
    ).json()
    assert Decimal(payload["data"]["rate_usd_per_gib"]) == settings.query_logs_scan_price_per_gb


def test_the_detail_carries_the_query_and_what_it_runs_against(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    detail = client.get(
        f"/api/v1/query/findings/{key(tenant_id, 'expensive')}", headers=auth(token)
    ).json()["data"]
    assert "filter @message like /ERROR/" in detail["query_text"]
    assert detail["targets"] == ["/aws/ecs/meter-api"]
    assert detail["region"] == "eu-west-2"


def test_an_unpublished_accuracy_is_null_rather_than_invented(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    # FEAT-018 publishes it. Until then the honest rendering is that it is not
    # published, which looks worse and is true.
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    detail = client.get(
        f"/api/v1/query/findings/{key(tenant_id, 'expensive')}", headers=auth(token)
    ).json()["data"]
    assert detail["accuracy_percent"] is None


def test_a_finding_nobody_has_is_the_same_404_as_one_out_of_scope(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Deliberate. A 403 here would confirm to an unauthorised caller that the
    row exists, which is the leak the status code is chosen to avoid."""
    seed(engine, tenant_id)
    unknown = client_for(engine, narrow(tenant_id), settings)
    missing = unknown[0].get(f"/api/v1/query/findings/{uuid4()}", headers=auth(unknown[1]))

    other = client_for(engine, narrow(another_tenant(engine)), settings)
    forbidden = other[0].get(
        f"/api/v1/query/findings/{key(tenant_id, 'expensive')}", headers=auth(other[1])
    )

    assert missing.status_code == forbidden.status_code == 404
    assert missing.json() == forbidden.json()


# --- instances ---------------------------------------------------------------


def test_an_unreachable_instance_reports_an_unknown_count_not_zero(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A zero would make the findings list look complete when it is not."""
    seed(engine, tenant_id)
    client, token = client_for(engine, narrow(tenant_id), settings)
    rows = client.get("/api/v1/query/instances", headers=auth(token)).json()["data"]
    broken = next(row for row in rows if not row["reachable"])
    assert broken["query_count"] is None
    assert broken["unreachable_reason"] == "the workspace returned 403"


def test_a_reachable_instance_reports_what_it_holds(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, narrow(tenant_id), settings)
    rows = client.get("/api/v1/query/instances", headers=auth(token)).json()["data"]
    working = next(row for row in rows if row["name"] == "workspace-reachable")
    assert working["query_count"] == 1


def test_a_workspace_that_was_read_and_holds_nothing_reports_zero(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Not null. The outer join gives null for "read it, found nothing" and for
    "could not read it", and rendering those the same way throws away the
    distinction the null exists to carry."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    rows = client.get("/api/v1/query/instances", headers=auth(token)).json()["data"]
    empty = next(row for row in rows if row["name"] == "workspace-self-hosted")
    assert empty["reachable"] is True
    assert empty["query_count"] == 0


def test_an_instance_in_an_account_out_of_scope_is_not_listed(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, narrow(tenant_id), settings)
    rows = client.get("/api/v1/query/instances", headers=auth(token)).json()["data"]
    assert [row["account_id"] for row in rows] == [IN_SCOPE, IN_SCOPE]


# --- the envelope ------------------------------------------------------------


def test_an_unreachable_workspace_makes_the_findings_list_partial(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The criterion this route exists to satisfy.

    Three of the tenant's four workspaces answered. The findings list is
    therefore missing an unknown number of rows, and the envelope has to say so:
    a total drawn from part of an estate that reports full coverage is the
    number a reader believes.
    """
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    coverage = client.get("/api/v1/query/findings", headers=auth(token)).json()["meta"][
        "scope_coverage"
    ]
    assert coverage == {"visible": 3, "total": 4, "is_partial": True, "unit": "workspaces"}


def test_coverage_counts_workspaces_rather_than_the_rows_on_the_page(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    # The instances route lists the unreachable workspace, so its row count is
    # four while its coverage is three. Counting the rows would report the gap
    # as covered by the very row that reports the gap.
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    payload = client.get("/api/v1/query/instances", headers=auth(token)).json()
    assert len(payload["data"]) == 4
    assert payload["meta"]["scope_coverage"]["visible"] == 3


def test_a_narrowed_scope_is_partial_against_the_whole_tenant(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Coverage is measured against the estate, not against what was permitted,
    which is ISS-016: a denominator computed from the visible set always
    reports full coverage."""
    seed(engine, tenant_id)
    client, token = client_for(engine, narrow(tenant_id), settings)
    coverage = client.get("/api/v1/query/findings", headers=auth(token)).json()["meta"][
        "scope_coverage"
    ]
    assert coverage == {"visible": 1, "total": 4, "is_partial": True, "unit": "workspaces"}


def test_an_unreadable_workspace_is_a_named_failure_on_the_envelope(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """A gap with no cause beside it is a gap the interface has to guess at, and
    it guessed wrong: it told the reader the missing part was outside their
    scope when Meter itself had been refused. ISS-152."""
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    meta = client.get("/api/v1/query/findings", headers=auth(token)).json()["meta"]
    (failure,) = [f for f in meta["failures"] if f["collector"] == "query_audit"]
    assert failure["cause"] == "the workspace returned 403"
    assert failure["scope_key"] == "workspace-unreachable"
    assert meta["degraded"] is True


def test_a_complete_estate_reports_no_failure_of_its_own(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    # The pair. Without it the assertion above would also pass on a route that
    # reported every workspace as broken.
    seed(engine, tenant_id)
    with engine.begin() as connection:
        connection.execute(
            models.grafana_instance.update()
            .where(models.grafana_instance.c.instance_id == key(tenant_id, "unreachable"))
            .values(reachable=True, unreachable_reason=None)
        )
    client, token = client_for(engine, everything(tenant_id), settings)
    meta = client.get("/api/v1/query/findings", headers=auth(token)).json()["meta"]
    assert [f for f in meta["failures"] if f["collector"] == "query_audit"] == []
    assert meta["scope_coverage"]["is_partial"] is False


def test_four_hundred_trivial_findings_surface_as_one_large_group(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The failure ADR-0016 names, and the reason grouping happens before
    ranking. Four hundred findings at 15 USD each are LOW individually and
    6,000 USD together, and a list ranked by individual severity puts the
    systemic problem below a single noisy panel."""
    seed(engine, tenant_id)
    instance = key(tenant_id, "reachable")
    with engine.begin() as connection:
        for index in range(400):
            query_id = key(tenant_id, f"trivial-{index}")
            connection.execute(
                models.query_definition.insert().values(
                    query_id=query_id,
                    tenant_id=tenant_id,
                    instance_id=instance,
                    origin="PANEL",
                    dashboard_uid="dash-many",
                    dashboard_title="One per team",
                    folder_uid="folder-1",
                    panel_id=f"panel-{index}",
                    ref_id="A",
                    engine="LOGS_INSIGHTS",
                    query_text="fields @timestamp",
                    fingerprint=str(query_id),
                    query_key=str(query_id),
                    target={"targets": ["/aws/ecs/meter-api"], "region": "eu-west-2"},
                    refresh_seconds=30,
                    range_seconds=2_592_000,
                    last_editor=None,
                    as_of=NOW,
                    collected_at=NOW,
                )
            )
            connection.execute(
                models.query_finding.insert().values(
                    finding_id=query_id,
                    tenant_id=tenant_id,
                    query_id=query_id,
                    run_date=NOW.date(),
                    runs_per_day=Decimal("2880.00"),
                    scan_bytes_per_run=1_000_000,
                    cost_month_usd=Decimal("15.00"),
                    provenance="modelled",
                    measured_runs=None,
                    severity="LOW",
                    cause="FAST_REFRESH",
                    why="Fast auto-refresh multiplies run count.",
                    as_of=NOW,
                    collected_at=NOW,
                )
            )

    client, token = client_for(engine, everything(tenant_id), settings)
    rows = client.get("/api/v1/query/findings", headers=auth(token)).json()["data"]
    assert all(row["severity"] == "LOW" for row in rows if row["cause"] == "FAST_REFRESH")

    groups = client.get("/api/v1/query/groups", headers=auth(token)).json()["data"]
    worst = groups[0]
    assert worst["cause"] == "FAST_REFRESH"
    assert worst["findings"] == 400
    assert Decimal(worst["monthly_cost"]) == Decimal("6000.00")
    # The group is CRITICAL although every finding in it is LOW. That is the
    # whole point: the threshold sees the systemic figure, not the row.
    assert worst["severity"] == "CRITICAL"


def test_a_group_is_ranked_on_its_total_not_on_its_worst_row(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    # The seeded estate holds one 180 USD finding and two at 24. Grouped by
    # cause, the ranking is by summed money.
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    groups = client.get("/api/v1/query/groups", headers=auth(token)).json()["data"]
    totals = [Decimal(group["monthly_cost"]) for group in groups]
    assert totals == sorted(totals, reverse=True)
    assert all(group["label"] != group["cause"] for group in groups)


def test_every_query_route_carries_meta(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    client, token = client_for(engine, everything(tenant_id), settings)
    for path in (
        "/api/v1/query/findings",
        f"/api/v1/query/findings/{key(tenant_id, 'expensive')}",
        "/api/v1/query/instances",
    ):
        payload = client.get(path, headers=auth(token)).json()
        assert set(payload["meta"]) >= {
            "as_of",
            "collected_at",
            "scope_coverage",
            "degraded",
            "failures",
        }, path
