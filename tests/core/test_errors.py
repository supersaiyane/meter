"""The error taxonomy is closed, and closed is the whole point.

ISS-015 names the single most likely defect in P0: a generic catch all error
appears, and within a release every failure is generic again. These tests exist
to make that regression impossible rather than discouraged.
"""

from __future__ import annotations

import pytest

from finops_core import errors

EXPECTED = {
    "AccessDenied",
    "Throttled",
    "NotOptedIn",
    "NoData",
    "Unreachable",
    "SchemaDrift",
}


def every_type() -> list[type[errors.CollectionError]]:
    return list(errors.CollectionError.__subclasses__())


def test_taxonomy_is_closed() -> None:
    assert {t.__name__ for t in every_type()} == EXPECTED


def test_taxonomy_has_no_second_level() -> None:
    """A subclass of a subclass is a catch all arriving by the back door."""
    for error_type in every_type():
        assert error_type.__subclasses__() == []


def test_every_error_carries_remediation() -> None:
    for error_type in every_type():
        raised = error_type(scope_key="acct:111111111111", collector="org_tree")
        assert raised.remediation.strip()
        assert raised.remediation != raised.cause


def test_every_error_carries_scope_and_collector() -> None:
    for error_type in every_type():
        raised = error_type(scope_key="acct:222222222222", collector="account_health")
        assert raised.scope_key == "acct:222222222222"
        assert raised.collector == "account_health"


def test_no_data_is_the_only_type_that_renders_as_zero() -> None:
    zeros = {t.__name__ for t in every_type() if t.renders_as_zero}
    assert zeros == {"NoData"}


def test_the_base_cannot_be_raised() -> None:
    """Without this, CollectionError is the catch all the taxonomy forbids."""
    with pytest.raises(TypeError):
        errors.CollectionError(scope_key="acct:333333333333", collector="x")


def test_message_names_the_cause_the_scope_and_the_collector() -> None:
    raised = errors.AccessDenied(
        scope_key="acct:444444444444", collector="cur_ingest", detail="assume role failed"
    )
    text = str(raised)
    assert "AccessDenied" in text
    assert "acct:444444444444" in text
    assert "cur_ingest" in text
    assert "assume role failed" in text


def test_detail_is_optional() -> None:
    raised = errors.Throttled(scope_key="acct:555555555555", collector="metrics")
    assert "acct:555555555555" in str(raised)


def test_cause_is_the_type_name() -> None:
    """The wire and the database store the cause, so it must not drift."""
    for error_type in every_type():
        assert error_type.cause == error_type.__name__


def test_arguments_are_keyword_only() -> None:
    """Positional arguments make a scope and a collector easy to swap silently."""
    with pytest.raises(TypeError):
        # Deliberately wrong, which is the assertion. The ignore is what lets
        # the type checker agree that it is wrong.
        errors.NoData("acct:666666666666", "org_tree")  # type: ignore[call-arg]
