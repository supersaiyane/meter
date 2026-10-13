#!/usr/bin/env bash
# Basic boiler Plate Doc | Grade A
# Why this file exists: Runs the admission gate whenever a dependency manifest changes.
# Grade A here: nothing in this file is specific to this project. Copy it unchanged.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
# Dependency admission gate, triggered by pre-commit when a manifest changes.
#
# Scans the resolved tree rather than the named package, because a manifest
# edit can pull in a transitive dependency the author never typed. Running the
# full scan here is the point: this is the moment a new dependency first
# reaches the repository.
#
# Skipping this hook is possible locally. The same gate runs in the pipeline on
# any manifest change, which is not skippable, so a skip only defers the answer.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "Dependency manifest changed. Running the admission gate."
echo "Policy is zero findings at any severity. See docs/05-SECURITY.md."
echo

exec bash "${ROOT}/scripts/security/scan.sh"
