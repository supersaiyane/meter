"""Two lists, one ratio, and a tracking list that keeps its refusals.

P5 spec sections 8 and 9. The cases that carry this file are the ones where the obvious
implementation is quietly reassuring.

**The coverage figure counts quotas, not accounts.** A reader whose whole organization is
visible, with three of seven quotas unmeasured, must not be told coverage is complete. The
plan says this would have been the fourth time a wrong count reached that slot, so it is
asserted on the unit as well as on the numbers.

**A quota nothing measured never renders as zero used.** It is in the second list, it has no
`used` field at all rather than a null one, and it carries the sentence saying why. A null
would invite a screen to draw it as zero and a caller to treat it as a number.

**The tracking list keeps what was refused.** A list showing only open requests answers the
question it exists for with silence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from finops_core.config import Settings
from finops_core.domain.tenant import Scope
from tests.api.test_query_routes import auth, client_for
from tests.api.test_waste_routes import everything, only

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 28, 6, 0, tzinfo=UTC)
LIST_PATH = "/api/v1/governance/quotas"
REQUESTS_PATH = "/api/v1/governance/quotas/requests"
MINE = "111122223333"
THEIRS = "444455556666"
REGION = "eu-west-1"

INSERT_RUN = text(
    "INSERT INTO ingest_run (run_id, tenant_id, collector, scope_key, idempotency_key, "
    "status, as_of_window_start, as_of_window_end) "
    "VALUES (:run, :t, 'quotas', 'scope', :key, 'SUCCEEDED', :at, :at)"
)
INSERT_QUOTA = text(
    "INSERT INTO quota_usage (quota_pk, tenant_id, ingest_run_id, sub_account_id, region_id, "
    "service_code, quota_code, quota_name, limit_value, used_value, usage_source, "
    "unmeasurable_reason, is_adjustable, as_of, collected_at) "
    "VALUES (:pk, :t, :run, :a, :region, :service, :quota, :name, :limit, :used, :source, "
    ":reason, :adjustable, :at, :at)"
)
INSERT_REQUEST = text(
    "INSERT INTO quota_request (request_pk, tenant_id, ingest_run_id, request_id, "
    "sub_account_id, region_id, service_code, quota_code, quota_name, desired_value, status, "
    "requested_at, last_updated_at, submitted_by_meter, as_of, collected_at) "
    "VALUES (:pk, :t, :run, :request, :a, :region, :service, :quota, :name, :desired, :status, "
    ":requested, :updated, FALSE, :at, :at)"
)
INSERT_HISTORY = text(
    "INSERT INTO quota_request_history (history_pk, tenant_id, request_id, status, changed_at) "
    "VALUES (:pk, :t, :request, :status, :changed)"
)

REASON = "Service Quotas declares no usage metric for this quota"
ADVISOR_REASON = (
    "Only Trusted Advisor reports usage for this quota, and it could not be read: "
    "NotOptedIn: the account has no Business support"
)

#: Four measured quotas at deliberately different headroom, three unmeasured for two different
#: reasons, and one of the unmeasured has no published limit either. That last one is the case
#: a screen is most likely to render as a zero of a zero.
QUOTAS: tuple[tuple[str, str | None, str, str, str, int | None, int | None, str, str | None], ...]
QUOTAS = (
    (MINE, REGION, "ec2", "L-1216C47A", "On-Demand vCPU", 320, 307, "AWS_USAGE_METRIC", None),
    (MINE, REGION, "lambda", "L-B99A9384", "Concurrency", 1000, 400, "AWS_USAGE_METRIC", None),
    (MINE, None, "iam", "L-FE177D64", "Roles per account", 1000, 212, "SERVICE_API", None),
    (MINE, REGION, "elb", "L-53DA6B97", "Load balancers", 50, 43, "TRUSTED_ADVISOR", None),
    (MINE, REGION, "ec2", "L-0EA8095F", "AMI sharing", 500, None, "NONE", REASON),
    (MINE, REGION, "rds", "L-7B6409FD", "DB instances", 40, None, "NONE", ADVISOR_REASON),
    (MINE, REGION, "kafka", "L-MSK", "Brokers", None, None, "NONE", REASON),
    # Another account's quota, so every scoped read has something it must not return.
    (THEIRS, REGION, "ec2", "L-1216C47A", "On-Demand vCPU", 64, 60, "AWS_USAGE_METRIC", None),
)

#: One open, one denied, and the denied one is for a quota nothing can measure. Tracking and
#: measuring are independent, and a fixture where every request named a measured quota would
#: leave that path exercised by nothing.
REQUESTS: tuple[tuple[str, str, str, str, int, str, int, int], ...] = (
    (MINE, "request-0001", "ec2", "L-1216C47A", 640, "PENDING", 10, 8),
    (MINE, "request-0002", "kafka", "L-MSK", 30, "DENIED", 40, 33),
    (THEIRS, "request-0003", "ec2", "L-1216C47A", 128, "APPROVED", 20, 15),
)


def seed(engine: Engine, tenant: UUID) -> None:
    with engine.begin() as connection:
        run = uuid4()
        connection.execute(INSERT_RUN, {"run": run, "t": tenant, "key": str(run), "at": NOW})
        for account, region, service, quota, name, limit, used, source, reason in QUOTAS:
            connection.execute(
                INSERT_QUOTA,
                {
                    "pk": uuid4(),
                    "t": tenant,
                    "run": run,
                    "a": account,
                    "region": region,
                    "service": service,
                    "quota": quota,
                    "name": name,
                    "limit": limit,
                    "used": used,
                    "source": source,
                    "reason": reason,
                    # The global one is a hard limit, so a draft must not be offered for it.
                    "adjustable": quota != "L-FE177D64",
                    "at": NOW,
                },
            )
        for account, request_id, service, quota, desired, status, made, moved in REQUESTS:
            connection.execute(
                INSERT_REQUEST,
                {
                    "pk": uuid4(),
                    "t": tenant,
                    "run": run,
                    "request": request_id,
                    "a": account,
                    "region": REGION,
                    "service": service,
                    "quota": quota,
                    "name": f"Quota {quota}",
                    "desired": desired,
                    "status": status,
                    "requested": NOW - timedelta(days=made),
                    "updated": NOW - timedelta(days=moved),
                    "at": NOW,
                },
            )
            # One row per status, deduplicated, because that is what the table allows: a
            # request still PENDING has one transition, not two identical ones. The first
            # version of this seeded both and the unique index refused it, which is the
            # index doing exactly what it is for.
            steps = (
                [(made, "PENDING")] if status == "PENDING" else [(made, "PENDING"), (moved, status)]
            )
            for offset, step in steps:
                connection.execute(
                    INSERT_HISTORY,
                    {
                        "pk": uuid4(),
                        "t": tenant,
                        "request": request_id,
                        "status": step,
                        "changed": NOW - timedelta(days=offset),
                    },
                )


def get(client: TestClient, token: str, path: str = LIST_PATH) -> dict[str, Any]:
    response = client.get(path, headers=auth(token))
    assert response.status_code == 200, f"{path} returned {response.status_code}: {response.text}"
    result = response.json()
    assert isinstance(result, dict)
    return result


class TestTheTwoLists:
    def test_measured_and_unmeasured_quotas_arrive_in_separate_lists(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, MINE), settings)
        data = get(client, token)["data"]
        assert len(data["measurable"]) == 4
        assert len(data["unmeasurable"]) == 3

    def test_no_unmeasured_quota_carries_a_usage_figure_at_all(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """Not a null and not a zero. The field is absent, so nothing can render it.

        This is spec exit criterion 2 asked of the payload rather than of the value: a
        response with `used: null` would satisfy every assertion about the number and still
        let a screen draw a bar at zero.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, MINE), settings)
        for row in get(client, token)["data"]["unmeasurable"]:
            assert "used" not in row
            assert "headroom" not in row
            assert "source" not in row

    def test_every_unmeasured_quota_says_why(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, MINE), settings)
        reasons = [row["reason"] for row in get(client, token)["data"]["unmeasurable"]]
        assert len(reasons) == 3
        assert all(reason.strip() for reason in reasons)
        # Two distinct reasons, because the estate has two distinct causes. One reason reused
        # for every row would pass a non empty check and tell a reader nothing.
        assert len(set(reasons)) == 2

    def test_the_least_headroom_is_first(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The only list in this product ordered by something other than money."""
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, MINE), settings)
        codes = [row["quota_code"] for row in get(client, token)["data"]["measurable"]]
        assert codes[0] == "L-1216C47A", "307 of 320 is the tightest quota and is not first"
        assert codes[-1] == "L-FE177D64", "212 of 1000 is the loosest and is not last"

    def test_a_quota_with_no_published_limit_keeps_a_null_limit(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The second absence, and it must not become a zero either."""
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, MINE), settings)
        rows = get(client, token)["data"]["unmeasurable"]
        no_limit = [row for row in rows if row["quota_code"] == "L-MSK"]
        assert len(no_limit) == 1
        assert no_limit[0]["limit"] is None

    def test_a_global_quota_carries_a_null_region(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """A placeholder here would let a screen show one limit once per region."""
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, MINE), settings)
        by_code = {row["quota_code"]: row for row in get(client, token)["data"]["measurable"]}
        assert by_code["L-FE177D64"]["region_id"] is None

    def test_adjustability_travels_so_a_draft_is_not_offered_against_a_hard_limit(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, MINE), settings)
        by_code = {row["quota_code"]: row for row in get(client, token)["data"]["measurable"]}
        assert by_code["L-FE177D64"]["is_adjustable"] is False
        assert by_code["L-1216C47A"]["is_adjustable"] is True


class TestTheCoverageFigure:
    def test_it_counts_quotas_and_says_so(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """TASK-P5-005's fourth criterion, asserted on the unit as well as the numbers.

        The unit is what stops the interface guessing. Every screen said "accounts" once,
        because the route knew what it had counted and the payload did not carry it.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, MINE), settings)
        coverage = get(client, token)["meta"]["scope_coverage"]
        assert coverage["unit"] == "quotas"
        assert coverage["visible"] == 4
        assert coverage["total"] == 7

    def test_a_reader_who_can_see_everything_is_still_told_coverage_is_partial(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The specific way an account denominator would be reassuring and wrong.

        Every account is visible, so an accounts based figure would report complete coverage
        while three of seven quotas had no usage figure at all. Counting quotas is what makes
        `degraded` true here, and `degraded` is what a screen reads.
        """
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        payload = get(client, token)
        coverage = payload["meta"]["scope_coverage"]
        assert coverage["visible"] < coverage["total"]
        assert coverage["is_partial"] is True
        assert payload["meta"]["degraded"] is True

    def test_the_counts_are_stated_in_the_body_as_well(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """Both lists are truncated, so a reader cannot derive the ratio by counting rows."""
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, MINE), settings)
        data = get(client, token)["data"]
        assert data["measured_count"] == 4
        assert data["found_count"] == 7


class TestScope:
    def test_a_narrowed_reader_sees_only_its_own_quotas(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, THEIRS), settings)
        data = get(client, token)["data"]
        assert {row["account_id"] for row in data["measurable"]} == {THEIRS}
        assert data["found_count"] == 1

    def test_a_narrowed_reader_sees_only_its_own_requests(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, THEIRS), settings)
        rows = get(client, token, REQUESTS_PATH)["data"]["requests"]
        assert {row["request_id"] for row in rows} == {"request-0003"}

    def test_an_empty_scope_sees_nothing_rather_than_everything(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        nothing = Scope(tenant_id=tenant_id, is_global=False, accounts=frozenset())
        client, token = client_for(engine, nothing, settings)
        data = get(client, token)["data"]
        assert data["measurable"] == []
        assert data["unmeasurable"] == []
        assert data["found_count"] == 0


class TestTheRequests:
    def test_refused_requests_are_returned_rather_than_filtered_out(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """A list showing only open requests answers its own question with silence."""
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, MINE), settings)
        rows = get(client, token, REQUESTS_PATH)["data"]["requests"]
        assert "DENIED" in {row["status"] for row in rows}

    def test_the_open_ones_come_first_and_are_counted(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, MINE), settings)
        payload = get(client, token, REQUESTS_PATH)["data"]
        assert payload["requests"][0]["status"] == "PENDING"
        assert payload["requests"][0]["is_open"] is True
        assert payload["open_count"] == 1

    def test_every_request_says_meter_did_not_submit_it(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """Constraint 6 as a field rather than as a sentence somebody could delete."""
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        rows = get(client, token, REQUESTS_PATH)["data"]["requests"]
        assert rows
        assert all(row["submitted_by_meter"] is False for row in rows)

    def test_a_request_for_an_unmeasurable_quota_is_tracked(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """Tracking and measuring are independent, which is the whole of TASK-P5-008."""
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, MINE), settings)
        tracked = {
            row["quota_code"] for row in get(client, token, REQUESTS_PATH)["data"]["requests"]
        }
        measured = {row["quota_code"] for row in get(client, token)["data"]["measurable"]}
        assert "L-MSK" in tracked
        assert "L-MSK" not in measured


class TestTheDetail:
    def test_it_returns_every_account_the_quota_applies_to(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """One row would answer a question about a slice nobody named."""
        seed(engine, tenant_id)
        client, token = client_for(engine, everything(tenant_id), settings)
        data = get(client, token, f"{LIST_PATH}/ec2/L-1216C47A")["data"]
        assert {row["account_id"] for row in data["measurable"]} == {MINE, THEIRS}

    def test_it_carries_the_status_history_so_a_reader_knows_when(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """The current status can say a request was approved but not when."""
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, MINE), settings)
        data = get(client, token, f"{LIST_PATH}/ec2/L-1216C47A")["data"]
        history = data["history"]["request-0001"]
        assert [entry["status"] for entry in history] == ["PENDING"]
        assert history[0]["changed_at"]

    def test_an_unmeasurable_quota_has_a_detail_page_too(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """Otherwise the longer of the two lists is a list of dead links."""
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, MINE), settings)
        data = get(client, token, f"{LIST_PATH}/kafka/L-MSK")["data"]
        assert data["measurable"] == []
        assert len(data["unmeasurable"]) == 1
        assert data["requests"][0]["status"] == "DENIED"

    def test_a_quota_nobody_collected_is_a_404_rather_than_an_empty_page(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """An empty page says the quota has no limits and no requests, which is a claim."""
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, MINE), settings)
        response = client.get(f"{LIST_PATH}/ec2/L-NOTHING", headers=auth(token))
        assert response.status_code == 404

    def test_another_accounts_quota_is_a_404_and_not_a_partial_answer(
        self, engine: Engine, tenant_id: UUID, settings: Settings
    ) -> None:
        """A reader scoped to one account asking about another's quota learns nothing."""
        seed(engine, tenant_id)
        client, token = client_for(engine, only(tenant_id, THEIRS), settings)
        response = client.get(f"{LIST_PATH}/kafka/L-MSK", headers=auth(token))
        assert response.status_code == 404
