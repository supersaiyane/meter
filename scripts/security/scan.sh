#!/usr/bin/env bash
# Basic boiler Plate Doc | Grade A
# Why this file exists: Runs every scanner and writes a timestamped report.
# Grade A here: nothing in this file is specific to this project. Copy it unchanged.
# Grades: A copy into a new project as is, no edits. B copy it and swap the
# names, paths or patterns named above. C leave behind, it is this project's
# own content rather than scaffolding, and is not tagged.
# Full security scan. Writes a timestamped report under security/reports/.
#
# Usage: scripts/security/scan.sh [--images] [--digest <sha256:...>]
#
#   default        scan the working tree: dependencies, secrets, terraform
#   --images       also build and scan the three container images
#   --digest       scan a specific deployed digest instead of a local build.
#                  This is what the nightly job uses. See security/README.md
#                  for why scanning the running digest matters more than
#                  scanning the build.
#
# Exit code 1 on any finding that is not covered by a valid allowlist entry.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAMP="$(date -u +%Y-%m-%d-%H%M%S)"
OUT="${ROOT}/security/reports/${STAMP}"
POLICY="${ROOT}/security/policy"
SCAN_IMAGES=0
DIGEST=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --images) SCAN_IMAGES=1; shift ;;
    --digest) DIGEST="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

mkdir -p "${OUT}"
echo "Report directory: ${OUT}"

# `make security-tools` installs pip-audit into the project venv, not onto PATH,
# so a scan run outside an activated venv reported it missing and stopped. The
# venv comes first, and PATH still works for the brew installed scanners.
if [[ -d "${ROOT}/.venv/bin" ]]; then
  PATH="${ROOT}/.venv/bin:${PATH}"
  export PATH
fi

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo >&2
    echo "MISSING TOOL: $1" >&2
    echo >&2
    echo "  This is a tooling problem, not a security finding." >&2
    echo "  Install every scanner with:  make security-tools" >&2
    echo "  Details: security/README.md" >&2
    echo >&2
    exit 2
  }
}

# ---------------------------------------------------------------- allowlist
# An expired allowlist entry must break the build rather than silently lapse
# into permanent acceptance. This runs first so an expired entry fails fast.
echo "==> Validating the allowlist"
python3 "${ROOT}/scripts/security/validate_allowlist.py" "${POLICY}/allowlist.yaml" \
  --emit-grype-ignore "${OUT}/grype-ignore.yaml"

# ---------------------------------------------------------------- secrets
echo "==> Scanning for secrets"
require gitleaks
# --config, so the false positives in .gitleaks.toml are declared in a file that
# explains each one, rather than being rediscovered on every scan. That file is
# scanner configuration; a real finding we choose to ship goes in
# security/policy/allowlist.yaml with an owner and an expiry instead.
gitleaks detect --source "${ROOT}" --config "${ROOT}/.gitleaks.toml" \
  --report-format json \
  --report-path "${OUT}/gitleaks.json" --redact --no-banner \
  || echo "gitleaks reported findings"
# The change being verified too, ISS-301. `detect` reads committed history, so a secret written
# in work not yet committed passed this gate and failed the next one, as a test fixture did on
# 2026-10-15. The files a commit would carry, changed since HEAD or new and not ignored, are
# copied out and scanned without git; the report reads every gitleaks*.json it finds.
PENDING="$(mktemp -d)"
python3 - "${ROOT}" "${PENDING}" <<'PY'
import os
import shutil
import subprocess
import sys

root, out = sys.argv[1], sys.argv[2]


def listed(*command: str) -> list[str]:
    found = subprocess.run(["git", "-C", root, *command], capture_output=True, check=True).stdout
    return [name.decode() for name in found.split(b"\0") if name]


changed = listed("diff", "-z", "--name-only", "HEAD")
for name in {*changed, *listed("ls-files", "-z", "--others", "--exclude-standard")}:
    source = os.path.join(root, name)
    if os.path.isfile(source) and not os.path.islink(source):
        target = os.path.join(out, name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)
PY
gitleaks detect --no-git --source "${PENDING}" --config "${ROOT}/.gitleaks.toml" \
  --report-format json \
  --report-path "${OUT}/gitleaks-pending.json" --redact --no-banner \
  || echo "gitleaks reported findings in uncommitted files"
rm -rf "${PENDING}"

# ---------------------------------------------------------------- python deps
if [[ -f "${ROOT}/pyproject.toml" ]]; then
  echo "==> Scanning Python dependencies"
  require pip-audit
  # The project directory, not the environment. Auditing the environment made
  # pip-audit try to look `meter` itself up on PyPI, and under --strict that is
  # an error rather than a finding, so the run aborted and no pip-audit.json was
  # written at all. Python dependencies were therefore absent from every summary
  # that claimed zero findings. Auditing `.` reads the declared dependencies,
  # keeps --strict, and produces a report.
  #
  # The runtime lock since ADR-0031, not `.`: auditing the declared ranges
  # resolved them afresh, so the report described the newest releases rather
  # than the versions every image actually installs. --no-deps because the lock
  # is already the whole closure, pinned.
  pip-audit --format json --output "${OUT}/pip-audit.json" --strict \
    --requirement "${ROOT}/requirements/runtime.lock" --require-hashes --no-deps \
    || echo "pip-audit reported findings"
fi

# ---------------------------------------------------------------- node deps
if [[ -f "${ROOT}/finops-web/package-lock.json" ]]; then
  echo "==> Scanning frontend dependencies"
  (cd "${ROOT}/finops-web" && npm audit --json > "${OUT}/npm-audit.json") \
    || echo "npm audit reported findings"
  # An npm finding accepted as development only holds while the package stays out of the
  # production tree, so the claim is checked here, beside the audit that raised it. ADR-0018.
  echo "==> Checking the development only acceptances"
  python3 "${ROOT}/scripts/ci/check_dev_only.py"
fi

# ---------------------------------------------------------------- terraform
if [[ -d "${ROOT}/infra/terraform" ]]; then
  echo "==> Scanning Terraform for misconfiguration"
  require trivy
  trivy config "${ROOT}/infra/terraform" --format json \
    --output "${OUT}/trivy-terraform.json" --config "${POLICY}/trivy.yaml" \
    || echo "trivy config reported findings"
fi

# ---------------------------------------------------------------- images
scan_image() {
  local name="$1" ref="$2"
  echo "==> SBOM for ${name}"
  syft "${ref}" -o spdx-json > "${ROOT}/security/sbom/${name}-${STAMP}.spdx.json"
  cp "${ROOT}/security/sbom/${name}-${STAMP}.spdx.json" "${OUT}/sbom-${name}.spdx.json"

  echo "==> grype ${name}"
  grype "${ref}" -o json --config "${POLICY}/grype.yaml" \
    > "${OUT}/grype-${name}.json" || echo "grype reported findings for ${name}"

  echo "==> trivy ${name}"
  trivy image "${ref}" --format json --output "${OUT}/trivy-${name}.json" \
    --config "${POLICY}/trivy.yaml" || echo "trivy reported findings for ${name}"
}

if [[ -n "${DIGEST}" ]]; then
  require grype; require syft; require trivy
  scan_image "deployed" "${DIGEST}"
elif [[ "${SCAN_IMAGES}" -eq 1 ]]; then
  require grype; require syft; require trivy
  for svc in api worker web; do
    scan_image "${svc}" "meter-${svc}:$(git -C "${ROOT}" rev-parse --short HEAD)"
  done
fi

# ---------------------------------------------------------------- report
echo "==> Building the HTML report"
python3 "${ROOT}/scripts/security/report.py" \
  --input "${OUT}" --allowlist "${POLICY}/allowlist.yaml" \
  --output "${OUT}/index.html" --summary "${OUT}/summary.json" \
  --posture "${ROOT}/security/POSTURE.md"

# Relative, because this link is committed. An absolute one stored the author's
# own home directory in the repository, so it resolved on exactly one machine.
# ISS-164.
ln -sfn "$(basename "${OUT}")" "${ROOT}/security/reports/latest"

# ---------------------------------------------------------------- gate
UNRESOLVED=$(python3 -c "import json,sys; print(json.load(open('${OUT}/summary.json'))['unresolved_total'])")
echo
echo "Report:  ${OUT}/index.html"
echo "Posture: ${ROOT}/security/POSTURE.md"

if [[ "${UNRESOLVED}" -gt 0 ]]; then
  echo
  echo "FAIL: ${UNRESOLVED} finding(s) not covered by a valid allowlist entry."
  echo "Run 'make security-fix' to apply the available upgrades, or add a"
  echo "time boxed allowlist entry with an owner. Do not change a threshold."
  exit 1
fi

echo
echo "PASS: zero unresolved findings."
