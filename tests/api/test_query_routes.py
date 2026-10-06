"""The three query governance routes, and the four ways they could mislead.

Ordering, because a page sorted in Python orders the page rather than the
estate. Scope, because a route that forgot its dependency must still not read
another tenant's findings. The published rate, because arithmetic with a
constant hidden in the frontend cannot be checked by the person reading it. And
the instance count, because an unreachable workspace reporting nought queries
makes an estate look smaller than it is.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4, uuid5

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

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


def client_for(
    engine: Engine, scope: Scope, settings: Settings, tickets: object | None = None
) -> tuple[TestClient, str]:
    signer = SessionSigner(SIGNING_KEY, ttl_hours=8, clock=lambda: NOW)
    app = create_app(
        engine=engine,
        entitlements=StubEntitlements(scope),
        signer=signer,
        settings=settings,
        # Defaulted to None, which is what the application ships with while
        # OPEN-05 is unanswered. A test that wants to assert on a ticket passes one.
        tickets=tickets,
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


def test_a_finding_audited_twice_is_listed_once(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """ISS-175. The audit keeps one row per query per day, and the list never
    filtered on it.

    Every finding therefore appeared once per day audited, and the grouped view
    added those days together, so the estate's reported cost grew by one estate
    per day. With a single day of data none of that is visible, which is why it
    survived every test until a second day existed.
    """
    seed(engine, tenant_id)
    with engine.begin() as connection:
        rows = connection.execute(
            text("SELECT query_id, cost_month_usd FROM query_finding WHERE tenant_id = :t"),
            {"t": tenant_id},
        ).all()
        for query_id, cost in rows:
            # Yesterday, at half the cost, so a read returning both shows as two
            # rows rather than as one repeated one.
            connection.execute(
                text(
                    "INSERT INTO query_finding (finding_id, tenant_id, query_id, run_date, "
                    "runs_per_day, scan_bytes_per_run, cost_month_usd, provenance, severity, "
                    "why, as_of, collected_at) VALUES (:id, :t, :q, :d, 1, 1, :c, 'modelled', "
                    "'low', 'yesterday', :now, :now)"
                ),
                {
                    "id": uuid4(),
                    "t": tenant_id,
                    "q": query_id,
                    "d": NOW.date() - timedelta(days=1),
                    "c": Decimal(cost) / 2,
                    "now": NOW,
                },
            )

    client, token = client_for(engine, everything(tenant_id), settings)
    listed = client.get("/api/v1/query/findings", headers=auth(token)).json()["data"]
    assert len(listed) == len(rows)

    grouped = client.get("/api/v1/query/groups", headers=auth(token)).json()["data"]
    assert sum(int(group["findings"]) for group in grouped) == len(rows)


def _adhoc(
    connection: object, tenant: UUID, day: object, runs: int, cost: str, fingerprint: str
) -> None:
    """One ad hoc row, on one day. The table is keyed on the day by design."""
    connection.execute(  # type: ignore[attr-defined]
        models.query_adhoc.insert().values(
            adhoc_id=uuid4(),
            tenant_id=tenant,
            account_id=IN_SCOPE,
            region_id="eu-west-2",
            fingerprint=fingerprint,
            query_text="fields @timestamp | filter @message like /timeout/",
            run_date=day,
            runs=runs,
            scan_bytes=1_000_000,
            cost_usd=Decimal(cost),
            principal="bob@example.com",
            as_of=NOW,
            collected_at=NOW,
        )
    )


def test_an_adhoc_query_seen_on_two_days_is_listed_once(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """ISS-177, which is ISS-175 on the table the fix did not reach.

    `query_adhoc` keeps one row per query per account, region and day, the same
    shape `query_finding` has and for the same reason. The list never filtered
    on the day, so a week of audits reported the same query seven times and its
    cost seven times over. One seeded day hides it completely, which is why it
    survived until an estate with a history existed to look at.

    The newest day wins rather than the largest. A query that ran less today
    than it did on Monday has got cheaper, and a list that quietly kept
    Monday's figure would be reporting a problem that has already gone away.
    """
    seed(engine, tenant_id)
    with engine.begin() as connection:
        _adhoc(connection, tenant_id, NOW.date() - timedelta(days=1), 90, "80.00", "fp-hand-01")
        _adhoc(connection, tenant_id, NOW.date(), 12, "9.00", "fp-hand-01")

    client, token = client_for(engine, everything(tenant_id), settings)
    rows = client.get("/api/v1/query/adhoc", headers=auth(token)).json()["data"]

    assert len(rows) == 1, f"one query audited twice came back {len(rows)} times"
    assert Decimal(rows[0]["cost_usd"]) == Decimal("9.00")
    assert rows[0]["runs"] == 12


def test_an_adhoc_query_nobody_ran_today_keeps_its_last_known_state(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Per query rather than one global maximum, matching `query_finding`.

    Somebody ran an expensive query on Monday and has not run it since. It is
    still the evidence that it happens, and dropping it because a different
    query ran more recently would make the estate look tidier than it is.
    """
    seed(engine, tenant_id)
    with engine.begin() as connection:
        _adhoc(connection, tenant_id, NOW.date() - timedelta(days=3), 200, "300.00", "fp-monday")
        _adhoc(connection, tenant_id, NOW.date(), 12, "9.00", "fp-today")

    client, token = client_for(engine, everything(tenant_id), settings)
    rows = client.get("/api/v1/query/adhoc", headers=auth(token)).json()["data"]

    assert len(rows) == 2
    # Worst first, and Monday's is still the worst.
    assert Decimal(rows[0]["cost_usd"]) == Decimal("300.00")


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
    assert coverage == {
        "visible": 3,
        "total": 4,
        "is_partial": True,
        "unit": "workspaces",
        "chosen": None,
    }


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
    assert coverage == {
        "visible": 1,
        "total": 4,
        "is_partial": True,
        "unit": "workspaces",
        "chosen": None,
    }


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


# --- remediation, FEAT-017 and the spec's two write routes -------------------


class Recording:
    """A `PanelRewrite` in memory that records what it was asked to change."""

    def __init__(self, drop_writes: bool = False) -> None:
        self.element: dict[str, object] = {"refresh_seconds": 10, "query": "fields @timestamp"}
        self.drop_writes = drop_writes
        self.writes: list[dict[str, object]] = []

    def read_element(self, _instance: object, _fingerprint: str) -> dict[str, object]:
        return dict(self.element)

    def write_element(
        self, _instance: object, _fingerprint: str, element: dict[str, object]
    ) -> None:
        self.writes.append(dict(element))
        if not self.drop_writes:
            self.element = dict(element)


def remediating_client(
    engine: Engine, scope: Scope, settings: Settings, control: object, level: str = "full"
) -> tuple[TestClient, str]:
    """A client whose deployment permits writes and has a control configured."""
    signer = SessionSigner(SIGNING_KEY, ttl_hours=8, clock=lambda: NOW)
    app = create_app(
        engine=engine,
        entitlements=StubEntitlements(scope),
        signer=signer,
        settings=settings.model_copy(update={"query_write_level": level}),
        remediation_control=control,
    )
    return TestClient(app, raise_server_exceptions=False), signer.issue(
        "p2", "someone@example.local", scope
    )


def violating(engine: Engine, tenant: UUID) -> UUID:
    """Make the expensive finding an explicit policy violation.

    The seeded one refreshes every ten seconds over thirty days, which already
    breaks the rule, and this states it rather than depending on the seed.
    """
    finding_id = key(tenant, "expensive")
    with engine.begin() as connection:
        connection.execute(
            models.query_definition.update()
            .where(models.query_definition.c.query_id == finding_id)
            .values(refresh_seconds=10, range_seconds=2_592_000)
        )
    return finding_id


def test_the_default_write_level_remediates_nothing(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """`none` is the default everywhere, and constraint 6 makes v1 read only.

    A refusal is reported rather than raised, so a caller can say why, and the
    control is never asked to do anything.
    """
    seed(engine, tenant_id)
    finding_id = violating(engine, tenant_id)
    control = Recording()
    client, token = remediating_client(
        engine, everything(tenant_id), settings, control, level="none"
    )
    body = client.post(f"/api/v1/query/remediate/{finding_id}", headers=auth(token)).json()
    assert body["data"]["applied"] is False
    assert "write level is none" in body["data"]["detail"]
    assert control.writes == []


def test_a_finding_that_is_not_a_violation_is_refused(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """The plan's own rule. A judgement call is a recommendation.

    Rewriting somebody's dashboard on a judgement call is how a remediation
    feature gets switched off for good.
    """
    seed(engine, tenant_id)
    finding_id = key(tenant_id, "expensive")
    with engine.begin() as connection:
        connection.execute(
            models.query_definition.update()
            .where(models.query_definition.c.query_id == finding_id)
            .values(refresh_seconds=3600, range_seconds=3600)
        )
    control = Recording()
    client, token = remediating_client(engine, everything(tenant_id), settings, control)
    body = client.post(f"/api/v1/query/remediate/{finding_id}", headers=auth(token)).json()
    assert body["data"]["applied"] is False
    assert "not an explicit policy violation" in body["data"]["detail"]
    assert control.writes == []


def test_a_permitted_remediation_raises_the_refresh_to_the_published_threshold(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    # The same number the reports warn at and the gate blocks on. A remediation
    # landing on a different one teaches a reader that neither is real.
    seed(engine, tenant_id)
    finding_id = violating(engine, tenant_id)
    control = Recording()
    client, token = remediating_client(engine, everything(tenant_id), settings, control)
    body = client.post(f"/api/v1/query/remediate/{finding_id}", headers=auth(token)).json()
    assert body["data"]["applied"] is True, body["data"]["detail"]
    assert body["data"]["change_id"] is not None
    assert control.element["refresh_seconds"] == settings.query_refresh_warn_seconds
    # Only the named field. Sending a whole element would overwrite anything a
    # person edited between the read and the write.
    assert control.element["query"] == "fields @timestamp"


def test_a_write_that_did_not_take_is_reverted_and_reported(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    finding_id = violating(engine, tenant_id)
    control = Recording(drop_writes=True)
    client, token = remediating_client(engine, everything(tenant_id), settings, control)
    body = client.post(f"/api/v1/query/remediate/{finding_id}", headers=auth(token)).json()
    assert body["data"]["applied"] is False
    assert body["data"]["reverted"] is True
    assert body["data"]["change_id"] is None


def test_a_deployment_with_no_control_says_so(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    # Rather than reporting success over a write nothing performed.
    seed(engine, tenant_id)
    finding_id = violating(engine, tenant_id)
    client, token = remediating_client(engine, everything(tenant_id), settings, None)
    body = client.post(f"/api/v1/query/remediate/{finding_id}", headers=auth(token)).json()
    assert body["data"]["applied"] is False
    assert "no remediation control" in body["data"]["detail"]


def test_undo_restores_what_the_remediation_replaced(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    finding_id = violating(engine, tenant_id)
    control = Recording()
    client, token = remediating_client(engine, everything(tenant_id), settings, control)
    client.post(f"/api/v1/query/remediate/{finding_id}", headers=auth(token))
    assert control.element["refresh_seconds"] == settings.query_refresh_warn_seconds

    body = client.post(f"/api/v1/query/remediate/{finding_id}/undo", headers=auth(token)).json()
    assert body["data"]["applied"] is True
    assert control.element["refresh_seconds"] == 10


def test_undo_with_nothing_applied_says_so_rather_than_failing(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    seed(engine, tenant_id)
    finding_id = violating(engine, tenant_id)
    client, token = remediating_client(engine, everything(tenant_id), settings, Recording())
    body = client.post(f"/api/v1/query/remediate/{finding_id}/undo", headers=auth(token)).json()
    assert body["data"]["applied"] is False
    assert "nothing to undo" in body["data"]["detail"]


def test_undoing_twice_is_refused(engine: Engine, tenant_id: UUID, settings: Settings) -> None:
    # The second would restore a state the first already replaced.
    seed(engine, tenant_id)
    finding_id = violating(engine, tenant_id)
    control = Recording()
    client, token = remediating_client(engine, everything(tenant_id), settings, control)
    client.post(f"/api/v1/query/remediate/{finding_id}", headers=auth(token))
    first = client.post(f"/api/v1/query/remediate/{finding_id}/undo", headers=auth(token)).json()
    second = client.post(f"/api/v1/query/remediate/{finding_id}/undo", headers=auth(token)).json()
    assert first["data"]["applied"] is True
    assert second["data"]["applied"] is False
    assert "nothing to undo" in second["data"]["detail"]


def test_another_tenant_cannot_remediate_this_finding(
    engine: Engine, tenant_id: UUID, settings: Settings
) -> None:
    """Scope is enforced before any write is attempted.

    A 404 rather than a 403, the same as the read route, so an unauthorised
    caller cannot use the status code to learn the row is there.
    """
    seed(engine, tenant_id)
    finding_id = violating(engine, tenant_id)
    control = Recording()
    client, token = remediating_client(engine, narrow(another_tenant(engine)), settings, control)
    response = client.post(f"/api/v1/query/remediate/{finding_id}", headers=auth(token))
    assert response.status_code == 404
    assert control.writes == []


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
