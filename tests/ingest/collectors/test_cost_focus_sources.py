"""Two sources in one table, and the bill's restatement removing only its own. TASK-P13-002.

From P13 the OpenAI and Anthropic collectors write to `cost_focus_daily` beside the bill. The
cost collector's restatement removes every row of a period its run did not write, and it never
writes a provider's rows, so without `ingest_source` the next AWS run would wipe them. P13 spec
section 5.3. Also here: the bill's AI columns reach the table, and the table's own constraints
hold the token columns together, constraint 11.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from finops_core.domain.cost import CostRecord
from finops_fakes.cur import (
    BEDROCK_SERVICE,
    CLOSED_PERIOD,
    ESTATE,
    FakeCostExport,
    bedrock_rows,
    restate,
)
from finops_ingest.collectors.cost_focus import COLUMNS, UPSERT, CostFocusCollector
from finops_ingest.collectors.partitions import ensure_partition
from finops_ingest.registry import CollectorContext

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 24, 6, 0, tzinfo=UTC)
#: OpenAI's source, as its collector names it from TASK-P13-004.
OPENAI = "openai"
CLOSED = tuple(row for row in ESTATE if row.billing_period_start == CLOSED_PERIOD)


@dataclass(frozen=True)
class Unit:
    tenant_id: UUID


@pytest.fixture(autouse=True, scope="module")
def _partitions(partition_sandbox: None) -> None:
    """This module creates partitions, so it gives them back. See conftest."""


def ingest(engine: Engine, tenant: UUID, export: object) -> tuple[int, int]:
    with engine.begin() as connection:
        ensure_partition(connection, "cost_focus_daily", CLOSED_PERIOD)
        outcome = CostFocusCollector(export, clock=lambda: NOW)(
            CollectorContext(unit=Unit(tenant_id=tenant), connection=connection, run_id=uuid4())
        )
    return int(outcome.items_written), int(outcome.items_removed)


def write(engine: Engine, row: CostRecord, tenant: UUID) -> None:
    """A row as another collector writes it, through the same statement."""
    values: dict[str, Any] = {column: getattr(row, column) for column in COLUMNS}
    values.update(tenant_id=tenant, ingest_run_id=uuid4(), tags=json.dumps(dict(row.tags)))
    with engine.begin() as connection:
        ensure_partition(connection, "cost_focus_daily", row.billing_period_start)
        connection.execute(UPSERT, [values])


def openai_line() -> CostRecord:
    """One of OpenAI's lines, which the bill's export never carries."""
    return replace(
        CLOSED[0],
        ingest_source=OPENAI,
        source_fingerprint="openai-line",
        billing_account_id="org-fake",
        sub_account_id="proj-fake",
        provider_name="OpenAI",
        service_name="OpenAI API",
        x_ai_model="gpt-fake",
        x_ai_token_type="input",
        x_ai_tokens=Decimal("1000"),
    )


def sources(engine: Engine, tenant: UUID) -> dict[str, int]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT ingest_source, count(*) FROM cost_focus_daily "
                "WHERE tenant_id = :t GROUP BY ingest_source"
            ),
            {"t": tenant},
        )
        return {source: int(count) for source, count in rows}


def test_a_providers_rows_survive_the_bills_restatement(engine: Engine, tenant_id: UUID) -> None:
    ingest(engine, tenant_id, FakeCostExport(rows=CLOSED))
    write(engine, openai_line(), tenant_id)

    _, removed = ingest(engine, tenant_id, FakeCostExport(rows=restate(CLOSED)))

    assert removed == 1, "the restatement withdrew one line of the bill and only that"
    assert sources(engine, tenant_id) == {"aws_export": len(CLOSED) - 1, "openai": 1}


def test_the_bills_rows_say_whose_they_are(engine: Engine, tenant_id: UUID) -> None:
    ingest(engine, tenant_id, FakeCostExport(rows=CLOSED))
    assert sources(engine, tenant_id) == {"aws_export": len(CLOSED)}


def test_the_bills_ai_columns_reach_the_table(engine: Engine, tenant_id: UUID) -> None:
    ingest(engine, tenant_id, FakeCostExport(rows=CLOSED, ai=True))
    with engine.connect() as connection:
        found = connection.execute(
            text(
                "SELECT x_ai_model, x_ai_token_type, sum(x_ai_tokens), "
                "array_agg(DISTINCT x_iam_principal) FROM cost_focus_daily "
                "WHERE tenant_id = :t AND service_name = :s GROUP BY x_ai_model, x_ai_token_type"
            ),
            {"t": tenant_id, "s": BEDROCK_SERVICE},
        ).all()
    expected = bedrock_rows(CLOSED)
    assert {(model, kind) for model, kind, _, _ in found} == {
        (row.x_ai_model, row.x_ai_token_type) for row in expected
    }
    assert sum(tokens for _, _, tokens, _ in found) == sum(row.x_ai_tokens or 0 for row in expected)
    principals = {principal for *_, group in found for principal in group}
    assert principals == {row.x_iam_principal for row in expected}


def test_the_bill_refuses_a_row_that_is_not_the_bills(engine: Engine, tenant_id: UUID) -> None:
    """A row written under another source could never be removed by this run's restatement."""
    with pytest.raises(ValueError, match="aws_export"):
        ingest(engine, tenant_id, FakeCostExport(rows=(openai_line(),)))


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"x_ai_tokens": Decimal("5"), "x_ai_token_type": None}, "tokens_have_a_type"),
        ({"x_ai_model": None, "x_ai_token_type": "input"}, "token_type_has_a_model"),
        ({"x_ai_tokens": Decimal("-1")}, "tokens_not_negative"),
        ({"ingest_source": "azure"}, "ingest_source"),
        ({"x_ai_token_type": "reasoning"}, "token_type"),
    ],
)
def test_the_table_holds_the_token_columns_together(
    engine: Engine, tenant_id: UUID, overrides: dict[str, object], constraint: str
) -> None:
    """Constraint 11. Written past the domain's own checks, straight at the table."""
    values: dict[str, Any] = {column: getattr(openai_line(), column) for column in COLUMNS}
    values.update(tenant_id=tenant_id, ingest_run_id=uuid4(), tags="{}", **overrides)
    with engine.begin() as connection:
        ensure_partition(connection, "cost_focus_daily", CLOSED_PERIOD)
    with pytest.raises(IntegrityError, match=constraint), engine.begin() as connection:
        connection.execute(UPSERT, [values])
