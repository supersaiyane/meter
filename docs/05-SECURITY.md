# Security

Last updated: 2026-08-23
Update trigger: any change to a control, a threshold, or the tool set
Reports and posture: `security/`

The deployment target is financial services. The posture is stated first,
because everything else follows from it.

## The rule

**Zero vulnerabilities, at any severity, at all times.**

Not zero critical. Not zero high. Zero.

A finding that genuinely cannot be fixed goes in
`security/policy/allowlist.yaml` with a named owner, a reason, and an expiry no
more than 90 days out. It never goes in by lowering a threshold, because a
lowered threshold is invisible and an expiring allowlist entry is not.

## The point that shapes every control below

**A zero vulnerability posture is not a build time property. It is a
continuously maintained one.**

A CVE published tomorrow against a dependency shipped today turns yesterday's
green build red, with no change to the code. A pipeline that scans only at
build time therefore reports zero forever while the deployed image degrades
silently.

So there are two scan cadences, and the second one matters more.

| Scan | When | Target |
| --- | --- | --- |
| Build scan | Every pipeline | The image being built |
| **Posture scan** | **Nightly** | **The digest actually running in each environment** |

`security/POSTURE.md` reflects the posture scan, not the last build.

## Controls

### 1. Base images

Minimus, from `reg.mini.dev`, built from upstream source with only runtime
dependencies included, and rebuilt continuously. See ADR-0010.

The comparison that makes the case: the official Python image ships with more
than 400 known vulnerabilities, around 70 of them high or critical, before a
single line of application code is added.

Two consequences that are easy to trip over.

- The runtime image has no shell and no package manager. Every `CMD` and
  `ENTRYPOINT` is in exec form. `docker exec` debugging is not available.
- `HEALTHCHECK` cannot use `curl` or `wget`. Health checking is done by the ALB
  target group, which is what ECS gates a rollout on anyway.

### 2. Dependency admission gate

No dependency is added until it scans clean, including its **whole transitive
tree**. Most vulnerable code arrives as a transitive dependency nobody chose.

```bash
make dep-check pkg=some-library
make dep-check pkg=some-package npm=1
```

The gate resolves the dependency into a throwaway environment, generates an
SBOM, and runs grype plus the ecosystem advisory scanner against everything it
pulled in. A pipeline job repeats this on any change to `pyproject.toml` or
`package-lock.json`, so the gate cannot be skipped by editing the file directly.

### 3. Scanners

Two vulnerability scanners, deliberately. Their databases differ, and the
difference is exactly where a missed finding lives. A finding seen by only one
is reported and labelled with which.

| Tool | Scans |
| --- | --- |
| `grype` | Container images and filesystems |
| `syft` | Generates the SBOM, which is the audit artefact |
| `trivy` | Second opinion, plus Terraform misconfiguration |
| `pip-audit` | Python dependencies against OSV |
| `npm audit` | Frontend dependencies |
| `gitleaks` | Secrets in the repository and its history |
| `cosign` | Signs images and attaches the SBOM attestation |

### 4. Report and fix

```bash
make security-scan       # everything, writes a timestamped report
make security-fix-dry    # what would be changed
make security-fix        # apply on a branch, run tests, re scan
```

The HTML report lists every unresolved finding with its severity, the package,
the installed and fixed versions, which scanners saw it, and **the exact
remediation command**. Allowlisted findings appear in their own section with
their owner and expiry, shown rather than hidden, because hiding them would
defeat the purpose of writing the entry down.

**On applying fixes automatically.** The requirement was that the fix should be
applied. It is, with one constraint that is not negotiable.

> Fixes are applied to a **branch** and gated on the **full test suite**. They
> are never applied to the default branch and never auto merged.

An unattended dependency upgrade that breaks production is a worse outcome than
the vulnerability it closed, and in a financial services environment the change
also has to be evidenced and approved. So the script does the tedious part in
full, patch and minor upgrades to a published fixed version, and a person
approves the merge. Major version bumps, findings with no published fix, and
transitive packages with no direct pin are proposed but never applied, because
each needs a judgement a script cannot make.

### 5. Supply chain

- Images signed with `cosign`, SBOM attached as an attestation.
- Base image digests pinned, and mirrored into the project's own ECR so a
  registry outage does not stop a deploy.
- GitLab OIDC into an AWS role. No long lived AWS key exists as a CI variable.
- Kaniko rather than docker-in-docker, so no privileged runner is needed.

### 6. Application security

Carried in the P0 design rather than here, because they are design properties
rather than scanning controls.

| Control | Where |
| --- | --- |
| Read only into member accounts, no write API call | ADR-0004 |
| Curated 40 action policy, never `ReadOnlyAccess` | ADR-0004, ISS-010 |
| ExternalId plus `aws:PrincipalOrgID` on every trust | ADR-0004 |
| Scope enforced at two independent points | P0 spec section 8, ISS-009 |
| Audit event on every scope evaluation | P0 spec section 5.5, ISS-031 |
| Local identity provider refuses to start in production | P0 spec section 11, ISS-017 |
| Secrets in Secrets Manager, never in an image layer | ADR-0010 |

## Where evidence lives

```
security/POSTURE.md               current posture, regenerated by every scan
security/reports/YYYY-MM-DD-.../  the full report for one scan
security/reports/latest/          symlink to the most recent
security/sbom/                    one SBOM per image per build
security/reviews/                 automated code review reports
security/policy/allowlist.yaml    time boxed exceptions, owner and expiry
```

Reports are committed, so the posture at any commit is reconstructable. An
auditor asking what was known on a given date gets an answer from the
repository rather than from a memory.

## Pipeline gates

| Stage | Gate | Blocks |
| --- | --- | --- |
| verify | `gitleaks`, `pip-audit`, `npm audit`, `trivy config` | yes |
| verify | dependency admission, on any manifest change | yes |
| build | `grype` and `trivy` on each built image | yes |
| build | `syft` SBOM, `cosign` signature | yes |
| nightly | posture scan against the running digest | raises an issue |

A nightly failure does not roll back a deployment on its own. It opens an issue
with the finding and the suggested fix, because an automatic rollback triggered
by a newly published advisory is its own outage risk.
