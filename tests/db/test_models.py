"""What the schema must guarantee, asserted against the metadata alone.

These need no database, so they run in `make test` and fail in seconds rather
than in the integration job. `tests/db/test_schema.py` then proves that the
migration actually produces this metadata, which is what ties the two together.

Constraint 11 in CLAUDE.md: an invariant is a database constraint, not a
convention. If application code is the only thing preventing a bad row, the bad
row eventually exists.
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import CheckConstraint, UniqueConstraint

from finops_api.db import models
from finops_core import errors

SPECIFIED_TABLES = {
    "tenant",
    "principal",
    "principal_scope",
    "cloud_account",
    "org_node",
    "ingest_run",
    "ingest_watermark",
    "sync_error",
    "cost_focus_daily",
    "cost_provider_extra",
    "platform_cost",
    "audit_event",
}


def constraint_text(table_name: str, constraint_name: str) -> str:
    table = models.metadata.tables[table_name]
    for constraint in table.constraints:
        if constraint.name == constraint_name:
            return str(getattr(constraint, "sqltext", ""))
    raise AssertionError(f"{table_name} has no constraint named {constraint_name}")


def test_every_table_from_the_specification_exists() -> None:
    assert set(models.metadata.tables) >= SPECIFIED_TABLES


def test_the_cadence_registry_is_present_too() -> None:
    """Constraint 9. Cadence is data, not code. ADR-0012."""
    assert "collector_schedule" in models.metadata.tables


def test_every_table_carries_tenant_id() -> None:
    """Adding it later means rewriting every query and index. Cheapest insurance here."""
    for table in models.metadata.tables.values():
        assert "tenant_id" in table.c, table.name


def test_cloud_account_has_no_email_column() -> None:
    """The account root email is personal data no feature reads. See docs/09."""
    assert "email" not in models.cloud_account.c


def test_the_idempotency_key_is_unique() -> None:
    """This, not application code, is what holds when two workers race. ISS-008."""
    unique = {
        tuple(c.name for c in constraint.columns)
        for constraint in models.ingest_run.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    # Per tenant, because the key does not carry the tenant and a global
    # constraint would make two tenants sharing an account collide.
    assert ("tenant_id", "idempotency_key") in unique


def test_every_fact_table_has_a_non_nullable_as_of() -> None:
    for name in models.FACT_TABLES:
        column = models.metadata.tables[name].c["as_of"]
        assert not column.nullable, name


def test_every_fact_table_has_a_non_nullable_collected_at() -> None:
    """Constraint 10. One timestamp cannot tell stale from fresh on its own."""
    for name in models.FACT_TABLES:
        column = models.metadata.tables[name].c["collected_at"]
        assert not column.nullable, name


def test_the_stored_error_types_mirror_the_closed_taxonomy() -> None:
    """A new cause cannot reach the database without a migration, on purpose."""
    in_code = {t.__name__ for t in errors.CollectionError.__subclasses__()}
    assert set(models.ERROR_TYPES) == in_code


def test_both_error_columns_are_constrained_to_that_set() -> None:
    for table, constraint in (
        ("ingest_run", "ck_ingest_run__error_type_valid"),
        ("sync_error", "ck_sync_error__type_valid"),
    ):
        text = constraint_text(table, constraint)
        for cause in models.ERROR_TYPES:
            assert cause in text, f"{table} does not admit {cause}"


def test_org_node_parent_is_a_self_referencing_foreign_key() -> None:
    """A node naming a parent that does not exist is an orphan nothing reports."""
    targets = {
        tuple(sorted(element.target_fullname for element in constraint.elements))
        for constraint in models.org_node.foreign_key_constraints
    }
    assert ("org_node.node_id", "org_node.tenant_id") in targets


def test_the_parent_foreign_key_is_deferrable() -> None:
    """The tree is rebuilt in one transaction, children before parents."""
    for constraint in models.org_node.foreign_key_constraints:
        if constraint.name == "fk_org_node__parent":
            assert constraint.deferrable is True
            assert constraint.initially == "DEFERRED"
            return
    raise AssertionError("fk_org_node__parent is missing")


def test_a_root_may_not_have_a_parent_and_a_non_root_must() -> None:
    text = constraint_text("org_node", "ck_org_node__root_has_no_parent")
    assert "ROOT" in text
    assert "parent_node_id" in text


def test_the_cost_tables_are_partitioned_by_billing_period() -> None:
    for table in (models.cost_focus_daily, models.cost_provider_extra):
        clause = table.dialect_options["postgresql"]["partition_by"]
        assert clause == "RANGE (billing_period_start)", table.name


def test_cloud_account_never_cascades() -> None:
    """An account leaving the organization must not silently drop its cost history."""
    for constraint in models.cloud_account.foreign_key_constraints:
        for element in constraint.elements:
            assert element.ondelete is None


def test_principal_scope_is_the_only_table_that_cascades() -> None:
    """It is a cache. Losing it costs one resolution, and an entry without an expiry
    would mean a revoked user keeps access."""
    cascading = {
        table.name
        for table in models.metadata.tables.values()
        for constraint in table.foreign_key_constraints
        for element in constraint.elements
        if element.ondelete == "CASCADE"
    }
    assert cascading == {"principal_scope"}
    assert not models.principal_scope.c["expires_at"].nullable


def test_the_scope_cache_names_exactly_one_target() -> None:
    text = constraint_text("principal_scope", "ck_principal_scope__one_target")
    assert "num_nonnulls" in text


def test_a_run_window_cannot_end_before_it_starts() -> None:
    text = constraint_text("ingest_run", "ck_ingest_run__window_ordered")
    assert "as_of_window_end" in text


def test_the_run_status_set_is_closed_and_includes_partial() -> None:
    """PARTIAL is the normal outcome at 300 accounts and must never read as success."""
    text = constraint_text("ingest_run", "ck_ingest_run__status_valid")
    for status in ("CLAIMED", "RUNNING", "SUCCEEDED", "FAILED", "PARTIAL"):
        assert status in text


def test_a_cadence_must_carry_a_reason() -> None:
    """A cadence without a recorded reason is a number nobody can safely change."""
    assert not models.collector_schedule.c["reason"].nullable


def test_a_sync_error_must_carry_a_remediation() -> None:
    """An error a user cannot act on without reading logs stays unfixed."""
    assert not models.sync_error.c["remediation"].nullable


def test_money_columns_are_numeric_and_never_float() -> None:
    for table_name, column_name in (
        ("cost_focus_daily", "billed_cost"),
        ("cost_focus_daily", "effective_cost"),
        ("platform_cost", "amortized_cost"),
    ):
        column = models.metadata.tables[table_name].c[column_name]
        assert isinstance(column.type, __import__("sqlalchemy").Numeric)


def test_check_constraints_carry_names() -> None:
    """An unnamed constraint cannot be dropped by a later migration."""
    for table in models.metadata.tables.values():
        for constraint in table.constraints:
            if isinstance(constraint, CheckConstraint):
                assert constraint.name, table.name


def test_the_stored_account_statuses_match_the_domain_enum() -> None:
    """A domain enum and a check constraint that disagree fail at the first write."""
    from finops_core.domain.account import AccountStatus

    assert set(models.ACCOUNT_STATUSES) == {member.value for member in AccountStatus}


def test_the_stored_node_types_match_the_domain_enum() -> None:
    from finops_core.domain.org import OrgNodeType

    assert set(models.NODE_TYPES) == {member.value for member in OrgNodeType}


def test_the_stored_role_health_values_match_the_domain_enum() -> None:
    """NOT_DEPLOYED and ACCESS_DENIED must both survive the round trip, separately."""
    from finops_core.domain.account import RoleHealth

    assert set(models.ROLE_HEALTH) == {member.value for member in RoleHealth}


def test_the_two_lifecycle_vocabularies_are_the_same_set() -> None:
    """ADR-0025's cost, held rather than hoped for.

    `commitment_action` exists because a payer wide finding cannot live in `recommendation`, and
    the price is that the lifecycle vocabulary is written down twice. Two vocabularies that
    drift is how one screen comes to mean something different by DONE.

    Compared at the source rather than in a running database, because the source is where a
    drift would be introduced and this way the failure arrives in the fast suite rather than
    only where Docker is available.

    If this fails the fix is not to relax it. Update both constraints, or, if a third payer wide
    finding class has appeared by then, move the vocabulary into a lookup table both reference,
    which is what ADR-0025 says to do at that point.
    """
    versions = Path(__file__).resolve().parents[2] / "migrations" / "versions"
    found: dict[str, frozenset[str]] = {}
    for path in sorted(versions.glob("*.py")):
        body = path.read_text(encoding="utf-8")
        for name in ("recommendation", "commitment_action"):
            match = re.search(
                rf"ck_{name}__lifecycle_known\s*\n?\s*CHECK \(lifecycle IN \(([^)]*)\)\)",
                body,
                re.DOTALL,
            )
            if match is not None:
                found[name] = frozenset(re.findall(r"'([A-Z_]+)'", match.group(1)))
    assert set(found) == {"recommendation", "commitment_action"}, (
        f"expected a lifecycle constraint for both tables, found {sorted(found)}"
    )
    assert found["recommendation"] == found["commitment_action"], (
        "the two lifecycle vocabularies have drifted: "
        f"{sorted(found['recommendation'] ^ found['commitment_action'])}"
    )
