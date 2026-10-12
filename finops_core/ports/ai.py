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
from finops_core.domain.ai import AiUsage, ProviderAccount
from finops_core.domain.cost import CostRecord


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


@runtime_checkable
class AiProviderReports(Protocol):
    """An AI provider's own reports of what one organization spent and used, TASK-P13-004.

    One adapter per provider, each reached with that organization's admin key, read at run time
    and never kept. Cost becomes FOCUS rows beside the cloud bill; usage becomes `AiUsage`.
    """

    def costs(
        self, account: ProviderAccount, start: datetime, end: datetime
    ) -> Iterable[CostRecord]:
        """Every daily cost line in `[start, end)`, as FOCUS rows naming the provider's source.

        Raises AccessDenied when the key is refused, Throttled when the provider keeps asking to
        slow down after the adapter's bounded retries, Unreachable when it cannot be reached or
        fails on its side, Misconfigured when the key cannot be read from where the account
        says it is, and SchemaDrift when a report lacks a field the mapping needs.
        """
        ...

    def usage(self, account: ProviderAccount, start: datetime, end: datetime) -> Iterable[AiUsage]:
        """Tokens and requests per day, model, project or workspace, key and user in `[start, end)`.

        Raises the same causes as `costs`: AccessDenied, Throttled, Unreachable, Misconfigured
        and SchemaDrift.
        """
        ...
