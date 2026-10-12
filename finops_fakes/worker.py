"""The local stack's worker: a deployment's process, on the fakes. TASK-P12-004.

`python -m finops_fakes.worker`. The same loop, SIGTERM handling and settling as a deployment's
worker, `finops_ingest.processes.worker_main`, with the fake composition and a broker that
assumes nothing, because a fake reads no account and needs no session.
"""

from __future__ import annotations

from typing import Any

from finops_core.domain.account import AccountKey
from finops_fakes.composition import fake_registry
from finops_ingest.processes import system_clock, worker_main


class NoSessions:
    """The local stack's credential broker: every account is reached with no session at all."""

    def __init__(self, _settings: Any = None) -> None:
        pass

    def session_for(self, _account: AccountKey, _region: str) -> None:
        return None


def main() -> int:
    return worker_main(lambda: fake_registry(system_clock), NoSessions)


if __name__ == "__main__":  # pragma: no cover - run as a process, and tested as one
    raise SystemExit(main())
