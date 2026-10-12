"""Which instance types are accelerated, and what a day of GPU utilization may say. FEAT-084.

TASK-P13-006. The type is read from its family, so a size added next year is still recognised,
and a row is held to percentages, at least one accelerator and a peak no lower than the average.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from finops_core.domain.ai import GpuUtilization, accelerated_instance_type


@pytest.mark.parametrize(
    ("usage_type", "instance_type"),
    [
        ("USE1-BoxUsage:g5.xlarge", "g5.xlarge"),
        ("EUW1-SpotUsage:p4d.24xlarge", "p4d.24xlarge"),
        ("USE1-DedicatedUsage:p5e.48xlarge", "p5e.48xlarge"),
        ("USE1-BoxUsage:g5g.xlarge", "g5g.xlarge"),
        ("USE1-BoxUsage:gr6.4xlarge", "gr6.4xlarge"),
        ("USE1-BoxUsage:trn1n.32xlarge", "trn1n.32xlarge"),
        ("USE1-BoxUsage:inf2.xlarge", "inf2.xlarge"),
        ("USE1-BoxUsage:dl1.24xlarge", "dl1.24xlarge"),
        # A SageMaker instance of the same family, billed under its own prefix.
        ("USE1-Notebk:ml.g5.xlarge", "g5.xlarge"),
        ("BoxUsage:g4dn.xlarge", "g4dn.xlarge"),
    ],
)
def test_an_accelerated_type_is_read_from_its_family(usage_type: str, instance_type: str) -> None:
    assert accelerated_instance_type(usage_type) == instance_type


@pytest.mark.parametrize(
    "usage_type",
    [
        "USE1-BoxUsage:m5.large",
        "USE1-BoxUsage:c7g.xlarge",
        "EUW1-EBS:VolumeUsage.gp3",
        "USE1-DataTransfer-Out-Bytes",
        "USE1-BoxUsage:gp3",
        "",
        None,
    ],
)
def test_anything_else_is_not_accelerated(usage_type: str | None) -> None:
    assert accelerated_instance_type(usage_type) is None


def day(**overrides: Any) -> GpuUtilization:
    values: dict[str, Any] = {
        "tenant_id": uuid4(),
        "account_id": "111122223333",
        "region_id": "eu-west-1",
        "instance_id": "i-1",
        "usage_date": date(2026, 10, 12),
        "gpu_count": 4,
        "average_percent": Decimal("40"),
        "peak_percent": Decimal("90"),
        "samples": 5760,
        "as_of": datetime(2026, 10, 13, tzinfo=UTC),
        "collected_at": datetime(2026, 10, 13, 6, tzinfo=UTC),
    }
    values.update(overrides)
    return GpuUtilization(**values)


@pytest.mark.parametrize(
    ("overrides", "says"),
    [
        ({"gpu_count": 0}, "at least one"),
        ({"samples": 0}, "at least one"),
        ({"average_percent": Decimal("-1")}, "percentage"),
        ({"peak_percent": Decimal("101")}, "percentage"),
        ({"average_percent": Decimal("95")}, "never below"),
    ],
)
def test_a_row_that_cannot_be_a_reading_is_refused(overrides: dict[str, Any], says: str) -> None:
    with pytest.raises(ValueError, match=says):
        day(**overrides)


def test_a_reading_is_kept_as_read() -> None:
    row = day()
    assert (row.gpu_count, row.average_percent, row.peak_percent) == (
        4,
        Decimal("40"),
        Decimal("90"),
    )
