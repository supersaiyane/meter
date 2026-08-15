#!/usr/bin/env bash
# Dependency admission gate. Run BEFORE adding a dependency, not after.
#
# Usage:
#   scripts/security/check_dependency.sh <python-package>[==version]
#   scripts/security/check_dependency.sh --npm <package>[@version]
#
# The rule, from ADR-0010: a dependency is added only if it scans with zero
# vulnerabilities. There is no severity threshold to argue about. A dependency
# that cannot pass is either replaced, or shipped behind a time boxed allowlist
# entry with a named owner, which is a decision a person makes and signs.
#
# The scan covers the whole transitive tree, not the named package alone. Most
# vulnerable code arrives as a transitive dependency nobody chose.
#
# Exit 0 clean, exit 1 findings, exit 2 tooling problem.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ECOSYSTEM="python"

if [[ "${1:-}" == "--npm" ]]; then
  ECOSYSTEM="npm"; shift
fi

PKG="${1:?usage: check_dependency.sh [--npm] <package>[==version]}"
WORK="$(mktemp -d)"
cleanup() { [[ -n "${WORK:-}" ]] && /bin/rm -r -f "${WORK}"; }
trap cleanup EXIT

echo "Admission gate: ${PKG} (${ECOSYSTEM})"
echo

if [[ "${ECOSYSTEM}" == "python" ]]; then
  python3 -m venv "${WORK}/venv" >/dev/null
  "${WORK}/venv/bin/pip" install --quiet --upgrade pip >/dev/null

  echo "==> Resolving into a throwaway environment"
  if ! "${WORK}/venv/bin/pip" install --quiet "${PKG}"; then
    echo "FAIL: ${PKG} does not install. Nothing to admit."
    exit 2
  fi

  "${WORK}/venv/bin/pip" list --format=freeze > "${WORK}/resolved.txt"
  echo "    transitive packages pulled in: $(wc -l < "${WORK}/resolved.txt" | tr -d " ")"

  echo "==> pip-audit"
  "${WORK}/venv/bin/pip" install --quiet pip-audit >/dev/null
  "${WORK}/venv/bin/pip-audit" --format json --output "${WORK}/pip-audit.json" || true

  echo "==> grype against the resolved tree"
  if command -v syft >/dev/null 2>&1 && command -v grype >/dev/null 2>&1; then
    syft "dir:${WORK}/venv" -o spdx-json > "${WORK}/sbom.json" 2>/dev/null
    grype "sbom:${WORK}/sbom.json" -o json \
      --config "${ROOT}/security/policy/grype.yaml" \
      > "${WORK}/grype-dependency.json" 2>/dev/null || true
  else
    echo "    grype or syft not installed. Install both, see security/README.md"
    exit 2
  fi
else
  echo "==> npm audit against a throwaway install"
  mkdir -p "${WORK}/npm"
  ( cd "${WORK}/npm" \
    && npm init -y >/dev/null 2>&1 \
    && npm install --package-lock-only "${PKG}" >/dev/null 2>&1 \
    && npm audit --json > "${WORK}/npm-audit.json" 2>/dev/null ) || true
fi

echo
python3 "${ROOT}/scripts/security/report.py" --gate-only \
  --input "${WORK}" \
  --allowlist "${ROOT}/security/policy/allowlist.yaml" \
  --label "${PKG}"
