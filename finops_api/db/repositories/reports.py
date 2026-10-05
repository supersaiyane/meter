"""Export records. FEAT-067, TASK-P8-009, P8 spec section 5.5 item 5.

Written here and read by the report library, TASK-P8-010. One function, because a record is one
insert, and an export that skipped it would be a copy of the estate nobody could trace.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.engine import Connection

from finops_api.db import models


def record_run(
    connection: Connection,
    *,
    tenant_id: UUID,
    principal_id: str,
    view_path: str,
    view_query: str,
    scope_accounts: Sequence[str] | None,
    file_format: str,
    rows: int,
    size: int,
    truncated: bool,
    made_at: datetime,
) -> UUID:
    """One row for one export file, in the transaction of the read it records.

    `scope_accounts` is None for a global scope and the named accounts otherwise, so a narrowed
    scope that named none is recorded as exactly that rather than as everything.
    """
    run_id = uuid4()
    connection.execute(
        models.report_run.insert().values(
            run_id=run_id,
            tenant_id=tenant_id,
            principal_id=principal_id,
            view_path=view_path,
            view_query=view_query,
            scope_global=scope_accounts is None,
            scope_accounts=[] if scope_accounts is None else sorted(scope_accounts),
            format=file_format,
            row_count=rows,
            byte_count=size,
            truncated=truncated,
            made_at=made_at,
        )
    )
    return run_id
