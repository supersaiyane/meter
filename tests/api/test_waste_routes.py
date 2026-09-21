"""The six P3 routes, called rather than imported.

TASK-P2-021 wrote six routes that imported cleanly, passed their tests and
returned 500 on every real call. Every test here goes through the client.

Two things carry this file. Whether a refused transition is a 409 with a useful
message rather than a 500, and whether the estimate and the realization can be
added together anywhere in these responses. The second is TASK-P3-014.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from finops_api.routes.waste import NO_RECOMMENDATIONS
from finops_core.config import Settings
from finops_core.domain.account import AccountKey, Provider
from finops_core.domain.tenant import Scope
from finops_fakes.recommendations import FakeRecommendationSource
from finops_fakes.tickets import FakeTicketSink
from finops_ingest.collectors.recommendations import RecommendationCollector
from finops_ingest.registry import CollectorContext
from tests.api.test_query_routes import auth, client_for

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 21, 6, 0, tzinfo=UTC)
LIST_PATH = "/api/v1/waste/recommendations"


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


def seed(engine: Engine, tenant: UUID) -> None:
    with engine.begin() as connection:
        RecommendationCollector(FakeRecommendationSource(), clock=lambda: NOW)(
            CollectorContext(unit=Unit(tenant_id=tenant), connection=connection, run_id=uuid4())
        )


def everything(tenant: UUID) -> Scope:
    return Scope(tenant_id=tenant, is_global=True, accounts=frozenset())


def only(tenant: UUID, account: str) -> Scope:
    return Scope(
        tenant_id=tenant,
        is_global=False,
        accounts=frozenset({AccountKey(provider=Provider.AWS, account_id=account)}),
    )


def get(client: TestClient, token: str, path: str = LIST_PATH) -> dict[str, Any]:
    response = client.get(path, headers=auth(token))
    assert response.status_code == 200, f"{path} returned {response.status_code}: {response.text}"
    result = response.json()
    assert isinstance(result, dict)
    return result


def first_id(client: TestClient, token: str) -> str:
    return str(get(client, token)["data"]["recommendations"][0]["recommendation_id"])


class TestTheListAnswers:
    def test_it_returns_an_envelope(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        payload = get(client, token)
        assert len(payload["data"]["recommendations"]) == 4
        assert payload["meta"]["as_of"]

    def test_the_biggest_money_is_first(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # Ranked by saving rather than confidence. A list ordered by confidence
        # puts a certain twenty dollars above an uncertain ten thousand.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        savings = [
            Decimal(row["estimated_monthly_saving"])
            for row in get(client, token)["data"]["recommendations"]
        ]
        assert savings == sorted(savings, reverse=True)

    def test_severity_and_confidence_are_two_fields(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The payload's version of the rule the entity enforces.

        A reader needs both to decide whether to act this week, and a single
        blended score would hide the finding most worth arguing about.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        row = get(client, token)["data"]["recommendations"][0]
        assert row["severity"] in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        assert row["confidence"] in {"HIGH", "MEDIUM", "LOW"}
        assert "score" not in row

    def test_unowned_recommendations_are_counted(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # ISS-021: an unowned finding is never fixed, so the count is surfaced
        # rather than left for somebody to notice.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        assert get(client, token)["data"]["unowned"] == 4

    def test_the_coverage_banner_counts_accounts(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # The fourth time a row count could have reached this slot. See
        # `tasks/lessons.md`.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        coverage = get(client, token)["meta"]["scope_coverage"]
        assert coverage["unit"] == "accounts"
        assert coverage["visible"] == 2

    def test_a_filter_narrows(self, engine: Engine, tenant_id: UUID, settings: Settings) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        filtered = get(client, token, f"{LIST_PATH}?waste_class=GRAVITON_CANDIDATE")
        assert len(filtered["data"]["recommendations"]) == 1


class TestScope:
    def test_a_narrow_reader_sees_fewer(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        whole, whole_token = client_for(engine, everything(tenant_id), settings)
        narrow, narrow_token = client_for(engine, only(tenant_id, "fake-platform-a"), settings)
        assert len(get(narrow, narrow_token)["data"]["recommendations"]) < len(
            get(whole, whole_token)["data"]["recommendations"]
        )

    def test_a_recommendation_out_of_scope_is_absent_rather_than_forbidden(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """A caller who could tell absent from forbidden could enumerate other
        accounts' recommendations by id."""
        seed(engine, tenant_id)
        whole, whole_token = client_for(engine, everything(tenant_id), settings)
        elsewhere = next(
            row["recommendation_id"]
            for row in get(whole, whole_token)["data"]["recommendations"]
            if row["account_id"] == "fake-platform-b"
        )
        narrow, narrow_token = client_for(engine, only(tenant_id, "fake-platform-a"), settings)
        response = narrow.get(f"{LIST_PATH}/{elsewhere}", headers=auth(narrow_token))
        assert response.status_code == 404


class TestTransitions:
    def test_accepting_names_an_owner_and_opens_a_ticket(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        tickets = FakeTicketSink()
        client, token = client_for(engine, everything(tenant_id), settings, tickets=tickets)
        identifier = first_id(client, token)
        response = client.post(
            f"{LIST_PATH}/{identifier}/accept?owner=alice@example.local", headers=auth(token)
        )
        assert response.status_code == 200
        found = response.json()["data"]["recommendation"]
        assert found["lifecycle"] == "ACCEPTED"
        assert found["owner"] == "alice@example.local"
        assert found["ticket_reference"]
        assert tickets.opened, "the ticket body should carry the working"

    def test_the_ticket_carries_the_working_and_the_money(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # A ticket saying only "rightsize i-0001" is one nobody can act on
        # without opening the product again.
        seed(engine, tenant_id)
        tickets = FakeTicketSink()
        client, token = client_for(engine, everything(tenant_id), settings, tickets=tickets)
        client.post(
            f"{LIST_PATH}/{first_id(client, token)}/accept?owner=alice@example.local",
            headers=auth(token),
        )
        _, body, _ = tickets.opened[0]
        assert "Estimated monthly saving" in body

    def test_every_transition_is_recorded(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        identifier = first_id(client, token)
        client.post(f"{LIST_PATH}/{identifier}/accept?owner=alice", headers=auth(token))
        history = get(client, token, f"{LIST_PATH}/{identifier}")["data"]["history"]
        assert [event["to_lifecycle"] for event in history] == ["OPEN", "ACCEPTED"]
        assert history[-1]["actor"]

    def test_an_illegal_transition_is_a_conflict_not_a_fault(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """409 with a message naming what is available instead.

        A refused move is a statement about this recommendation's state, not an
        error in the request or the server.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        identifier = first_id(client, token)
        client.post(f"{LIST_PATH}/{identifier}/dismiss?reason=wontfix", headers=auth(token))
        # DISMISSED moves only back to OPEN, never straight to ACCEPTED.
        response = client.post(f"{LIST_PATH}/{identifier}/accept?owner=alice", headers=auth(token))
        assert response.status_code == 409
        assert "does not move to" in response.json()["detail"]

    def test_a_dismissal_without_a_reason_is_refused_by_the_route(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # The route, the service and the database all require it. A dismissal
        # nobody can review is indistinguishable from one nobody looked at.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        response = client.post(
            f"{LIST_PATH}/{first_id(client, token)}/dismiss", headers=auth(token)
        )
        assert response.status_code == 422

    def test_accepting_without_an_owner_is_refused(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        response = client.post(f"{LIST_PATH}/{first_id(client, token)}/accept", headers=auth(token))
        assert response.status_code == 422

    def test_no_ticket_sink_configured_still_accepts(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """OPEN-05 is unanswered and the lifecycle works anyway.

        A product refusing to accept a recommendation because nobody had picked a
        ticketing system would be holding its own feature hostage.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        response = client.post(
            f"{LIST_PATH}/{first_id(client, token)}/accept?owner=alice", headers=auth(token)
        )
        assert response.status_code == 200
        assert response.json()["data"]["recommendation"]["ticket_reference"] is None


class TestTheOtherTwoFilters:
    """The list takes three filters and only one of them had a test.

    Each `if` in the repository is a branch that can be written the wrong way
    round, and a filter silently matching nothing looks identical to an estate
    with nothing in it.
    """

    def test_a_lifecycle_filter_narrows(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        client.post(
            f"{LIST_PATH}/{first_id(client, token)}/accept?owner=alice", headers=auth(token)
        )
        accepted = get(client, token, f"{LIST_PATH}?lifecycle=ACCEPTED")
        still_open = get(client, token, f"{LIST_PATH}?lifecycle=OPEN")
        assert len(accepted["data"]["recommendations"]) == 1
        assert len(still_open["data"]["recommendations"]) == 3

    def test_an_owner_filter_narrows(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # The filter a person uses to find their own queue, which is the only
        # reason ISS-021's unowned count is worth surfacing at all.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        client.post(
            f"{LIST_PATH}/{first_id(client, token)}/accept?owner=alice", headers=auth(token)
        )
        mine = get(client, token, f"{LIST_PATH}?owner=alice")
        somebody_else = get(client, token, f"{LIST_PATH}?owner=bob")
        assert len(mine["data"]["recommendations"]) == 1
        assert somebody_else["data"]["recommendations"] == []


class TestTheTransitionContract:
    def test_a_transition_on_an_unknown_recommendation_is_a_404(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The scoped read happens before the move, not inside it.

        Otherwise a caller outside the scope would learn from the error message
        whether an id existed, which is the enumeration this refuses.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        response = client.post(f"{LIST_PATH}/{uuid4()}/accept?owner=alice", headers=auth(token))
        assert response.status_code == 404
        assert response.json()["detail"] == NO_RECOMMENDATIONS

    def test_the_transitions_carry_no_body(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """Asserted against the published schema rather than against a call.

        A body that works today and is optional tomorrow is how two ways to
        dismiss a recommendation appear, and only one of them would be the one
        with the audit trail.
        """
        seed(engine, tenant_id)
        client, _ = client_for(engine, everything(tenant_id), settings)
        paths = client.get("/openapi.json").json()["paths"]
        for route in (
            "/api/v1/waste/recommendations/{recommendation_id}/accept",
            "/api/v1/waste/recommendations/{recommendation_id}/dismiss",
        ):
            assert "requestBody" not in paths[route]["post"], route


class TestTheTwoNumbersCannotBeAdded:
    """TASK-P3-014, asserted at the boundary rather than described in a document."""

    def test_no_recommendation_carries_a_realized_figure(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        for row in get(client, token)["data"]["recommendations"]:
            for forbidden in ("realized_monthly_saving", "cost_before", "cost_after", "verdict"):
                assert forbidden not in row

    def test_no_saving_carries_an_estimate(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        client, token = client_for(engine, everything(tenant_id), settings)
        payload = get(client, token, "/api/v1/waste/savings")
        for row in payload["data"]["savings"]:
            assert "estimated_monthly_saving" not in row

    def test_realized_money_is_grouped_by_verdict_rather_than_totalled(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """A single realized total would be added to the estimated total by the
        first person who saw them side by side, and an inconclusive saving is not
        a saving."""
        client, token = client_for(engine, everything(tenant_id), settings)
        data = get(client, token, "/api/v1/waste/savings")["data"]
        assert "total" not in data
        assert "realized_total" not in data
        assert isinstance(data["by_verdict"], dict)

    def test_the_two_figures_are_served_by_different_routes(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # The structural half. No single response holds both, so adding them takes
        # two calls and a deliberate decision rather than a careless join.
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        estimates = get(client, token)["data"]
        realized = get(client, token, "/api/v1/waste/savings")["data"]
        assert "savings" not in estimates
        assert "recommendations" not in realized


class TestTheSavingsRouteOverRealRows:
    """Every other savings test runs against an empty table, which hid a crash.

    The route called `Decimal(row.usage_before)` on a column migration `0012` made
    nullable, so the first unobserved control would have been a 500 rather than a
    null. Nothing caught it, because no test had put a row in `realized_saving`.
    """

    def a_verdict(
        self,
        engine: Engine,
        tenant: UUID,
        *,
        verdict: str,
        usage: Decimal | None,
    ) -> UUID:
        with engine.begin() as connection:
            identifier = connection.execute(
                text("SELECT recommendation_id FROM recommendation WHERE tenant_id = :t LIMIT 1"),
                {"t": tenant},
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO realized_saving (realized_id, recommendation_id, tenant_id, "
                    "window_before_start, window_before_end, window_after_start, "
                    "window_after_end, cost_before, cost_after, usage_before, usage_after, "
                    "verdict, why, as_of, collected_at) "
                    "VALUES (:id, :rec, :t, '2026-06-01', '2026-07-01', '2026-07-31', "
                    "'2026-08-30', 100, 60, :usage, :usage, :verdict, 'the working', :at, :at)"
                ),
                {
                    "id": uuid4(),
                    "rec": identifier,
                    "t": tenant,
                    "usage": usage,
                    "verdict": verdict,
                    "at": NOW,
                },
            )
        assert isinstance(identifier, UUID)
        return identifier

    def test_an_unobserved_control_serializes_as_null_not_zero(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """Constraint 5, at the last boundary before a person reads it.

        A zero here would say the workload went away. The whole chain, billing rows
        to collector to column to response, has to carry the null, and this is the
        end of it.
        """
        seed(engine, tenant_id)
        self.a_verdict(engine, tenant_id, verdict="INCONCLUSIVE", usage=None)
        client, token = client_for(engine, everything(tenant_id), settings)
        row = get(client, token, "/api/v1/waste/savings")["data"]["savings"][0]
        assert row["usage_before"] is None
        assert row["usage_after"] is None
        assert row["verdict"] == "INCONCLUSIVE"

    def test_a_measured_control_serializes_as_a_figure(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # The other direction, so the null above is not simply what this route
        # returns for every row.
        seed(engine, tenant_id)
        self.a_verdict(engine, tenant_id, verdict="VERIFIED", usage=Decimal("720"))
        client, token = client_for(engine, everything(tenant_id), settings)
        row = get(client, token, "/api/v1/waste/savings")["data"]["savings"][0]
        assert Decimal(row["usage_before"]) == Decimal("720")

    def test_the_inconclusive_rows_are_listed_rather_than_hidden(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """ISS-029. The inconclusive verdicts are the evidence this is not a vanity
        metric, so they appear in the list and in the totals."""
        seed(engine, tenant_id)
        self.a_verdict(engine, tenant_id, verdict="INCONCLUSIVE", usage=None)
        client, token = client_for(engine, everything(tenant_id), settings)
        data = get(client, token, "/api/v1/waste/savings")["data"]
        assert [row["verdict"] for row in data["savings"]] == ["INCONCLUSIVE"]
        assert "INCONCLUSIVE" in data["by_verdict"]


class TestTheScoreRoute:
    """FEAT-043 at the boundary. The components arrive with the total or not at all.

    A second call for the components is a second call a screen can decline to make,
    which is how a decomposable score becomes a number on its own by the time anybody
    reads it.
    """

    SCORE_PATH = "/api/v1/waste/score"

    def an_account(self, engine: Engine, tenant: UUID, account: str) -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO cloud_account (account_pk, tenant_id, provider, account_id, "
                    "name, status, as_of, collected_at) "
                    "VALUES (:pk, :t, 'aws', :a, :a, 'ACTIVE', :at, :at) ON CONFLICT DO NOTHING"
                ),
                {"pk": uuid4(), "t": tenant, "a": account, "at": NOW},
            )

    def a_score(
        self,
        engine: Engine,
        tenant: UUID,
        account: str,
        *,
        total: int,
        coverage_points: str | None = "20",
    ) -> UUID:
        score_id = uuid4()
        self.an_account(engine, tenant, account)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO finops_score (score_id, tenant_id, sub_account_id, team, "
                    "total, available_weight, why, as_of, collected_at) "
                    "VALUES (:id, :t, :a, NULL, :total, 100, 'the working', :at, :at)"
                ),
                {"id": score_id, "t": tenant, "a": account, "total": total, "at": NOW},
            )
            for name, points, weight in (
                ("waste", "30", 40),
                ("coverage", coverage_points, 20),
                ("responsiveness", "25", 25),
                ("verification", "15", 15),
            ):
                connection.execute(
                    text(
                        "INSERT INTO finops_score_component (component_id, score_id, tenant_id, "
                        "name, points, weight, why, as_of, collected_at) "
                        "VALUES (:c, :id, :t, :name, :points, :weight, 'the working', :at, :at)"
                    ),
                    {
                        "c": uuid4(),
                        "id": score_id,
                        "t": tenant,
                        "name": name,
                        "points": None if points is None else Decimal(points),
                        "weight": weight,
                        "at": NOW,
                    },
                )
        return score_id

    def test_a_score_arrives_with_its_components(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        self.a_score(engine, tenant_id, "fake-platform-a", total=70)
        client, token = client_for(engine, everything(tenant_id), settings)
        payload = get(client, token, self.SCORE_PATH)
        row = payload["data"]["scores"][0]
        assert row["total"] == 70
        assert row["available_weight"] == 100
        assert {part["name"] for part in row["components"]} == {
            "waste",
            "coverage",
            "responsiveness",
            "verification",
        }
        assert payload["meta"]["as_of"]

    def test_the_worst_score_is_first(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # A list sorted best first is a list nobody scrolls, and the account at the
        # bottom is the one the reader came for.
        self.a_score(engine, tenant_id, "fake-platform-a", total=80)
        self.a_score(engine, tenant_id, "fake-platform-b", total=30)
        client, token = client_for(engine, everything(tenant_id), settings)
        totals = [row["total"] for row in get(client, token, self.SCORE_PATH)["data"]["scores"]]
        assert totals == sorted(totals)

    def test_a_component_that_could_not_be_computed_serializes_as_null(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The last boundary before a reader sees it.

        A zero would say this dimension scored nothing, which is the worst possible
        posture, for a dimension nobody could measure.
        """
        self.a_score(engine, tenant_id, "fake-platform-a", total=70, coverage_points=None)
        client, token = client_for(engine, everything(tenant_id), settings)
        row = get(client, token, self.SCORE_PATH)["data"]["scores"][0]
        coverage = next(part for part in row["components"] if part["name"] == "coverage")
        assert coverage["points"] is None
        assert coverage["weight"] == 20

    def test_an_account_with_no_score_is_listed_rather_than_omitted(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # An account nobody could assess is different from an account with a bad
        # score, and a shorter league table is not something anybody notices.
        self.a_score(engine, tenant_id, "fake-platform-a", total=70)
        self.an_account(engine, tenant_id, "fake-platform-z")
        client, token = client_for(engine, everything(tenant_id), settings)
        data = get(client, token, self.SCORE_PATH)["data"]
        assert [row["account_id"] for row in data["scores"]] == ["fake-platform-a"]
        assert "fake-platform-z" in data["unscored"]

    def test_only_the_newest_score_per_account_is_served(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The history exists and the list is not it.

        Two rows for one account, six hours apart. A list showing both would double
        every account on the screen and sort the same account against itself.
        """
        self.a_score(engine, tenant_id, "fake-platform-a", total=40)
        score_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO finops_score (score_id, tenant_id, sub_account_id, team, "
                    "total, available_weight, why, as_of, collected_at) "
                    "VALUES (:id, :t, 'fake-platform-a', NULL, 90, 100, 'later', :at, :at)"
                ),
                {"id": score_id, "t": tenant_id, "at": NOW + timedelta(hours=6)},
            )
        client, token = client_for(engine, everything(tenant_id), settings)
        scores = get(client, token, self.SCORE_PATH)["data"]["scores"]
        assert len(scores) == 1
        assert scores[0]["total"] == 90


class TestWhenThereIsNothing:
    def test_an_unknown_recommendation_is_a_404(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        client, token = client_for(engine, everything(tenant_id), settings)
        response = client.get(f"{LIST_PATH}/{uuid4()}", headers=auth(token))
        assert response.status_code == 404

    def test_an_estate_with_no_findings_returns_an_empty_list_and_says_so(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        # Distinct from the detail route's 404. A list of nothing is a true
        # statement about an estate that has been looked at; the meta carries
        # whether anything was ever collected.
        client, token = client_for(engine, everything(tenant_id), settings)
        payload = get(client, token)
        assert payload["data"]["recommendations"] == []
        assert payload["data"]["unowned"] == 0
