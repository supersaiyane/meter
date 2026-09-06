"""Attribution, and the difference between measured and modelled.

Two things are worth failing over here. An unowned finding is never fixed,
which is ISS-021, so the principal reader is tested against every shape
CloudTrail produces. And a figure a reader cannot tell apart from an estimate
is treated as an estimate, so every upgrade from modelled to measured has to
say so in words the reader sees.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from finops_query import ownership


@pytest.mark.parametrize(
    ("identity", "expected"),
    [
        ({"userName": "alex"}, "alex"),
        ({"principalId": "AROAEXAMPLE:alex"}, "alex"),
        ({"sessionContext": {"sessionIssuer": {"userName": "DeployRole"}}}, "DeployRole"),
        ({"arn": "arn:aws:sts::000000000000:assumed-role/Reader/alex"}, "alex"),
        ({"type": "AssumedRole"}, "AssumedRole"),
    ],
)
def test_a_principal_is_read_from_whichever_field_carries_it(
    identity: dict[str, Any], expected: str
) -> None:
    """Five shapes, depending on how the caller authenticated."""
    assert ownership.principal_from({"userIdentity": identity}) == expected


def test_the_most_recognisable_name_wins() -> None:
    """A user name beats a role name beats an ARN fragment beats a type."""
    identity = {
        "userName": "alex",
        "principalId": "AROAEXAMPLE:someone-else",
        "type": "AssumedRole",
    }

    assert ownership.principal_from({"userIdentity": identity}) == "alex"


def test_an_unidentifiable_event_returns_nothing_rather_than_a_placeholder() -> None:
    """An unowned finding should read as unowned, not as owned by "unknown"."""
    assert ownership.principal_from({}) is None
    assert ownership.principal_from({"userIdentity": {}}) is None


def measured_bundle(**logs: Any) -> dict[str, Any]:
    return {"lookback_days": 7, "logs": dict(logs)}


def test_an_exact_query_matches_its_own_executions() -> None:
    bundle = measured_bundle(**{"fields @message": {"runs": 14, "bytes": 0.0, "runs_bytes": []}})

    found = ownership.match_observed("FIELDS  @message", bundle)

    assert found is not None
    assert found.runs == 14


def test_a_templated_query_collects_the_runs_of_every_value_it_took() -> None:
    """Without this, measured counts never attach to templated panels, which
    are most of the expensive ones."""
    bundle = measured_bundle(
        **{
            "filter region = 'eu-west-1'": {"runs": 5, "bytes": 0.0, "runs_bytes": []},
            "filter region = 'us-east-1'": {"runs": 3, "bytes": 0.0, "runs_bytes": []},
            "filter service = 'api'": {"runs": 99, "bytes": 0.0, "runs_bytes": []},
        }
    )

    found = ownership.match_observed("filter region = '$region'", bundle)

    assert found is not None
    assert found.runs == 8, "the unrelated query must not be swept in"


def test_matched_keys_are_recorded_so_the_remainder_is_not_lost() -> None:
    """Whatever is left is a query somebody ran by hand. It is a real cost with
    no dashboard to attribute it to, and dropping it understates the account."""
    bundle = measured_bundle(
        **{
            "filter a = 1": {"runs": 2, "bytes": 0.0, "runs_bytes": []},
            "filter b = 2": {"runs": 4, "bytes": 0.0, "runs_bytes": []},
        }
    )

    ownership.match_observed("filter a = 1", bundle)

    assert bundle["_matched_keys"] == {"filter a = 1"}


def test_nothing_measured_matches_nothing() -> None:
    assert ownership.match_observed("anything", {"lookback_days": 7, "logs": {}}) is None


def test_measured_bytes_replace_the_ingestion_assumption_entirely() -> None:
    """The whole value of measuring. A modelled Logs Insights figure rests on an
    assumed ingestion rate that can be an order of magnitude out."""
    bundle = measured_bundle(
        **{"q": {"runs": 7, "bytes": 7 * (1024**3), "runs_bytes": [1024**3] * 7}}
    )

    found = ownership.measure_logs_query("q", 999.0, bundle, price_per_gb=0.005)

    assert found is not None
    assert found.bytes_measured is True
    assert found.bytes_per_run == 1024**3
    assert found.runs_per_day == 1.0
    assert found.cost_month == pytest.approx(1.0 * 1.0 * 30.0 * 0.005)
    assert "MEASURED" in found.reason


def test_runs_can_be_measured_while_bytes_stay_modelled() -> None:
    """Better than nothing, and not the same as measured. The reason says which."""
    bundle = measured_bundle(**{"q": {"runs": 14, "bytes": 0.0, "runs_bytes": []}})

    found = ownership.measure_logs_query("q", 1024**3, bundle, price_per_gb=0.005)

    assert found is not None
    assert found.bytes_measured is False
    assert found.runs_per_day == 2.0
    assert "bytes modelled" in found.reason


def test_a_query_with_no_observed_runs_is_not_upgraded() -> None:
    """Zero measured runs is not evidence that the query costs nothing."""
    bundle = measured_bundle(**{"q": {"runs": 0, "bytes": 0.0, "runs_bytes": []}})

    assert ownership.measure_logs_query("q", 1.0, bundle, price_per_gb=0.005) is None


def test_metric_calls_are_attributed_by_namespace_and_metric() -> None:
    bundle = {"lookback_days": 7, "gmd_by_metric": {"aws/ec2|cpuutilization": 700}}

    found = ownership.measure_metric_query(
        "AWS/EC2", "AWS/EC2 CPUUtilization", bundle, metrics_per_call=1.0, price_per_1000=0.01
    )

    assert found is not None
    assert found.runs_per_day == 100.0
    assert found.runs_total == 700
    assert "CloudTrail" in found.reason


def test_a_metric_panel_with_no_namespace_is_not_attributed() -> None:
    """Matching on the metric name alone would attach another panel's calls."""
    bundle = {"lookback_days": 7, "gmd_by_metric": {"aws/ec2|cpuutilization": 700}}

    assert (
        ownership.measure_metric_query(
            "", "CPUUtilization", bundle, metrics_per_call=1.0, price_per_1000=0.01
        )
        is None
    )


def test_a_lookback_of_zero_days_does_not_divide_by_zero() -> None:
    bundle = {"lookback_days": 0, "logs": {"q": {"runs": 5, "bytes": 0.0, "runs_bytes": []}}}

    found = ownership.measure_logs_query("q", 1.0, bundle, price_per_gb=0.005)

    assert found is not None
    assert found.runs_per_day == 5.0


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "0 B"), (512, "512 B"), (1024, "1.0 KB"), (1024**3, "1.0 GB"), (1536 * 1024**2, "1.5 GB")],
)
def test_bytes_are_rendered_for_a_person(count: int, expected: str) -> None:
    assert ownership.human_bytes(count) == expected


class TestResolveOwner:
    """The precedence, and the refusal to invent one.

    The order is an argument about who will act, not about who is most likely to
    be named. A folder mapping is a team saying they own what is inside it; a
    last editor touched the thing and can explain it; a CloudTrail principal
    merely ran it, which for a dashboard panel can be anyone who opened the page.
    """

    MAP: ClassVar[dict[str, str]] = {"folder-platform": "platform@example.com"}

    def test_the_folder_map_wins(self) -> None:
        owner = ownership.resolve_owner(
            folder_uid="folder-platform",
            folder_map=self.MAP,
            last_editor="bob@example.com",
            principal="carol@example.com",
        )
        assert owner == ownership.Owner("platform@example.com", ownership.FOLDER_MAP)

    def test_the_last_editor_is_next(self) -> None:
        owner = ownership.resolve_owner(
            folder_uid="folder-unmapped",
            folder_map=self.MAP,
            last_editor="bob@example.com",
            principal="carol@example.com",
        )
        assert owner == ownership.Owner("bob@example.com", ownership.LAST_EDITOR)

    def test_cloudtrail_is_the_last_resort(self) -> None:
        owner = ownership.resolve_owner(
            folder_uid=None,
            folder_map={},
            last_editor=None,
            principal="carol@example.com",
        )
        assert owner == ownership.Owner("carol@example.com", ownership.CLOUDTRAIL)

    def test_nothing_resolvable_is_unowned_rather_than_defaulted(self) -> None:
        # A wrongly assigned owner is ignored by the person it reaches and never
        # reaches the person who could act.
        owner = ownership.resolve_owner(
            folder_uid=None, folder_map={}, last_editor=None, principal=None
        )
        assert owner == ownership.Owner(None, None)
        assert owner.is_owned is False

    def test_an_empty_string_does_not_count_as_an_owner(self) -> None:
        # A blank read out of a column is an absence, not a name.
        owner = ownership.resolve_owner(
            folder_uid="", folder_map={"": ""}, last_editor="", principal=""
        )
        assert owner.is_owned is False

    def test_an_owner_never_arrives_without_the_source_that_produced_it(self) -> None:
        for folder, editor, principal in (
            ("folder-platform", None, None),
            (None, "bob@example.com", None),
            (None, None, "carol@example.com"),
            (None, None, None),
        ):
            owner = ownership.resolve_owner(
                folder_uid=folder,
                folder_map=self.MAP,
                last_editor=editor,
                principal=principal,
            )
            assert (owner.email is None) == (owner.source is None)
