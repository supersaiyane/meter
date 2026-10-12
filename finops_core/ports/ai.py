"""Reading who spent tokens on which model, P13.

Defined in TASK-P13-003. The bill says what a model cost and never who called it; these say who
called what, and how many tokens and requests it took. A cost per caller is modelled from them
and the bill, never read from them, because only the bill knows the price that was paid.

**Never a prompt or a response.** Constraint 6 keeps Meter read only, and P13's first rule keeps
it further: an adapter reads aggregates, so nothing a caller sent a model ever reaches Meter.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol, runtime_checkable

from finops_core.domain.account import AccountKey
from finops_core.domain.ai import AiUsage


@runtime_checkable
class InvocationLogs(Protocol):
    """Bedrock's record of the calls made in one account and Region, read as daily aggregates."""

    def usage(
        self, account: AccountKey, region: str, start: datetime, end: datetime
    ) -> Iterable[AiUsage]:
        """Requests and tokens per day, caller, model and application, for `[start, end)`.

        A day with no calls yields no row, which is a measured nothing, distinct from an account
        whose calls cannot be read at all. Raises NotOptedIn when the account's invocation logging
        names no CloudWatch Logs group; AccessDenied when the role may not read the logging
        configuration or start a query on the group; Misconfigured when the group the
        configuration names does not exist or the application key is not a key; Throttled when
        Logs Insights refuses another query; and SchemaDrift when a result row lacks a field the
        aggregate names.
        """
        ...
