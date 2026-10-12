"""The local stack's dispatcher: a deployment's process, on the fakes. TASK-P12-004.

`python -m finops_fakes.dispatcher`. ADR-0022 keeps the fakes out of the runtime image, so this
entry point, rather than a setting, is what puts a process on them, and it runs only where
`finops_fakes` is installed: the local stack and the tests. The wall clock is handed in from
`finops_ingest.processes`, because nothing in this package reads it.
"""

from __future__ import annotations

from finops_fakes.composition import fake_registry
from finops_ingest.processes import dispatcher_main, system_clock


def main() -> int:
    return dispatcher_main(lambda: fake_registry(system_clock))


if __name__ == "__main__":  # pragma: no cover - run as a process, and tested as one
    raise SystemExit(main())
