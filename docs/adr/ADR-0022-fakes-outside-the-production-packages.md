# ADR-0022: The fakes live outside the production packages

Date: 2026-09-21
Status: Accepted

## Context

From P0 until 2026-09-21 the in memory port implementations lived in
`finops_providers/fake/`, a sibling of `finops_providers/aws/`. That put them
inside a package the runtime image copies whole, so every deployed image carried
a module whose job is to fabricate a bill, beside the module whose job is to
report a real one.

Nothing in `finops_core`, `finops_query`, `finops_ingest`, `finops_api` or
`finops_mcp` ever imported one. The discipline was real and held for three sub
projects. What was missing was any structure or check that made it hold, so it
held because the people writing the code remembered, which is the weakest form of
a rule.

Three things made the question worth settling rather than leaving.

**The fakes grew.** P3 added the generated utilization estate: 36 resources, two
years of hourly behaviour, a planted findings oracle, and the topology, quota and
container estates for P4, P5 and P6. The package went from nine modules to
eighteen, and from a set of stubs to a substantial artefact with its own tests.

**The image is the security boundary.** `security/POSTURE.md` and the Minimus base
images exist to make the runtime surface small and arguable. A module that
generates cost data is not part of a product that reports cost data, and it is
easier to say so than to explain why it is present and unreachable.

**Read only in v1 is a claim about the image.** Constraint 6 says no write API call
into a member account. A reader checking that claim reads what the image contains,
and a fake estate in there is a paragraph of explanation rather than an absence.

## Decision

The fakes move to a top level `finops_fakes/` package, and three separate
mechanisms keep them out of production:

1. **Not in the wheel.** `[tool.setuptools.packages.find]` names six packages and
   `finops_fakes` is not one of them, so `pip install .` does not install it and
   the runtime image cannot import it whatever the source tree contains.
2. **Forbidden by contract.** An import-linter contract named "production code
   never imports a fake" lists the six production packages as sources and
   `finops_fakes` as forbidden. It fails the build, not a review.
3. **Linted to the same standard.** `finops_fakes` is in `PY_PKGS`, so ruff, ruff
   format and mypy see it exactly as they see production code.

The third is not ceremony. A fake nobody checks drifts from the port it stands in
for, and then the tests pass against behaviour the real adapter does not have. The
`read_many` widening in P3 is the example: the port grew a method, the fake
provider stopped satisfying it, and a type check caught what a reviewer would not
have.

The two scripts that need the fakes, `seed_demo.py` and `export_fake_estate.py`,
move from `scripts/ops/` to `scripts/demo/`. `scripts/ops/` is copied into the
image because it holds tooling a person runs against a live database, including
the erasure procedure `docs/09-DATA-CLASSIFICATION.md` commits to. A demo seeder
is not that, and keeping the two directories apart makes the image's contents a
consequence of where a file lives rather than of a comment.

## What this forced, and improved

`make seed`, `make unseed` and `make migrate` ran inside the api container. The
seed cannot any more, because the image no longer carries what it imports, so all
three now run from the working tree against the exposed Postgres port.

That is a better arrangement for a reason unrelated to this decision. The image
bakes the source in at build time, so a compose `run` executes whatever the tree
looked like at the last `make up`. On 2026-09-21 `make migrate` exited zero having
applied nothing, and `make seed` then reported writing 2292 rows through the same
stale image, while the local database sat four revisions behind. Every test passed
throughout, because the suite migrates its own throwaway database from the working
tree. Running from the tree cannot drift, and the lesson in `tasks/lessons.md`
about asserting the alembic head rather than the exit code now describes a trap
that has been removed rather than one to remember.

## What was rejected

**Leaving them where they were and relying on the import contract alone.** The
contract would have been enough to stop production code importing a fake, and it
would not have kept the fake out of the image. Two of the three reasons above are
about what the image contains rather than about what the code does.

**A `tests/fakes/` directory.** The fakes are not only used by tests: the demo
seeder writes a whole estate with them, and the demo is a product surface. Under
`tests/` they would be awkward to import from `scripts/`, and the naming would say
something untrue about what they are for.

**A separate distribution.** Correct at a larger scale and premature here. A second
package with its own version means a version skew between the fake and the port it
implements, which is the one failure the contract and the shared linting exist to
prevent.

## Consequences

A new production package has to be added to the forbidden contract's source list by
hand. That is a gap: a seventh package would be unprotected and nothing would say
so. It is smaller than the gap it replaces, and worth watching.

`PYTHONPATH` is the working tree in the seed targets, because `finops_fakes` is
importable from the repository and from nowhere else. That is the same rule as the
forbidden contract, arriving from the other direction.

Eleven checkpoint resume vectors named the old path and were rewritten, which
`make check-memory` refused to let pass. A resume vector pointing at a file that
does not exist is not a historical record, it is a dead end.
