# ADR-0031: Dependencies are installed from a lock, never resolved

Date: 2026-10-06
Status: Accepted
Relates to: ISS-253, ADR-0010, CHG-0113

## Context

`pyproject.toml` declares ranges with no upper bound, `sqlalchemy>=2.0` among them, and nothing
pinned the versions. Every install resolved PyPI afresh: `make setup`, four CI jobs and both
Python images. The versions the gate had proven existed only in whichever virtualenv happened to
be built. The base images were already pinned by digest, ADR-0010; the Python packages were the
one part of the build that floated.

On 2026-10-06 a `uv run` call resolved the project again and moved 31 packages under a working
tree: SQLAlchemy 2.0 to 2.1.3, FastAPI to 0.142, Starlette to 1.7, Pydantic to 2.13 and the MCP
SDK to 2.3. mypy then failed 154 checks, measured, in code nobody had touched. CI would have met
the same on its next fresh install, with no change in the repository to explain it.

## Decision

**Two locks, written from `pyproject.toml` with hashes.** `requirements/dev.lock` holds 115 pins
and `requirements/runtime.lock` 58, both measured on 2026-10-06. `make lock` writes them with
`uv pip compile`, universal, so one file serves a macOS laptop and the `linux/amd64` images. The
runtime lock is compiled against the dev lock as a constraint, so an image runs exactly the
versions the tests ran.

**Installed by pip, every pin checked against its hash.** `make setup` and `make sync`, the four
CI jobs and both Python images install the lock with `--require-hashes`, then the project with
`--no-deps`, then run `pip check`. A dependency in `pyproject.toml` that is missing from the lock
fails that check rather than resolving silently.

**uv writes the lock and nothing else.** `[tool.uv] managed = false` stops `uv run` resolving the
project and syncing the environment. uv is needed only to rewrite the lock; CI and the images need
only pip.

**The scan audits what ships.** pip-audit reads `requirements/runtime.lock` with hashes and
`--no-deps`, where it used to resolve `.` and so describe the newest releases rather than the
versions an image installs.

**An upgrade is a change of its own.** `make lock-upgrade`, then `make sync`, then `make verify`,
in one commit.

The first lock was written at the releases of 2026-10-06, the owner's choice that day over
restoring the August versions, and it carried the upgrade with it: 92 annotations moved to
SQLAlchemy 2.1's variadic `Select` and `Row`, two counts read through `Any`, one `DISTINCT ON`
moved to `postgresql.distinct_on`, and two stale type ignores removed. On the lock, measured: mypy
clean over 451 files, and 3,007 backend tests passed.

## Consequences

- A fresh clone, CI and the images install the same versions, each checked against its hash, and
  a release published after the lock was written cannot reach a build.
- Adding a dependency is `make dep-check pkg=name`, then `pyproject.toml`, then `make lock`.
- Every upgrade shows as a diff of the lock and passes the gate before it lands.
- After pulling a change to the lock, `make sync` brings an existing virtualenv to it.
- Tools rather than dependencies still float: what `make security-tools` installs, and the
  `pip install pyyaml` lines of the two CI jobs that need nothing else. Known and accepted.

## Alternatives considered

- **Restore the August versions without a lock.** Rejected: CI and the images still floated, so
  the same failure would return on the next fresh install.
- **Upper bounds in `pyproject.toml`.** Rejected: patch releases still float, and bounds hide an
  upgrade rather than make it deliberate.
- **uv's own project lock and `uv sync` everywhere.** Rejected: it puts uv into CI and the image
  builder, where the requirements format keeps pip as the only installer.
- **pip-tools.** The same result as a new dev dependency; uv was already the resolver at hand.
