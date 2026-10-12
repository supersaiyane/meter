# Security

<!-- Basic boiler Plate Doc | Grade B
     Why this file exists: The security policy: what is scanned, by what, at which gate, and
     what blocks a merge.
     Grade B here: copy it, then replace the specifics. The gate structure carries over.
     Grades: A copy into a new project as is, no edits. B copy it and swap the
     names, paths or patterns named above. C leave behind, it is this project's
     own content rather than scaffolding, and is not tagged.
-->

Last updated: 2026-08-23
Update trigger: any change to a control, a threshold, or the tool set
Reports and posture: `security/`

The deployment target is financial services. The posture is stated first,
because everything else follows from it.

## The rule

**Zero findings that have a published fix.** Amended 2026-08-23 by ADR-0018,
after TASK-P0-029 measured the base images and found the previous wording,
zero at any severity, could not be met by any Python image that exists.

Two registers, and the difference between them matters.

| Register | For | Expires |
| --- | --- | --- |
| `policy/allowlist.yaml` | A finding that **has** a fix we are temporarily not taking | Yes, 90 days maximum |
| `policy/accepted.yaml` | A finding with **no published fix**, where no rebuild helps | No. It carries a review date instead |

An acceptance requires a **reachability argument**: why the vulnerable code
path does not exist in Meter. "We accept the risk" is not one. Where the
argument can be enforced it must be, and
`scripts/ci/check_forbidden_imports.py` fails the build if anyone imports a
module an acceptance depends on not importing. `scripts/ci/check_dev_only.py`,
run by `scan.sh` beside the npm audit, fails it if a package accepted because it
is only a development dependency appears in npm's production tree; the web image
carries the built `dist` and nothing from `node_modules`. The first such package
was `source-map-js`, GHSA-68fv-2mgg-jv7q, accepted on 2026-10-06.

A threshold is never lowered. A lowered threshold is invisible, and both an
expiring allowlist entry and a reviewable acceptance record are not.

### What measurement showed, and why version choice matters more than policy

| Image | Total | Critical | High | Fixable |
| --- | --- | --- | --- | --- |
| `python:3.12` | 13 | 0 | 3 | 0 |
| **`python:3.13`** | **3** | 0 | **0** | 0 |
| **`node:22-dev`** | **0** | 0 | 0 | 0 |
| `nginx:1.27` | 93 | 6 | 26 | 76 |
| **`nginx:1.30`** | **0** | 0 | 0 | 0 |
| official `python:3.12-slim` | 204 | 7 | 26 | 80 |

Two moves nobody had suggested, found only by scanning, removed 3 High and 93
findings. **Choose the version by measurement.** No policy wording achieves
that, and it achieved more here than any wording would have.

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

## Where a finding is caught, and where it is stopped

Six layers. They are not equivalent, and it matters which ones actually stop
something.

| # | Layer | When | Can it stop a deploy | Skippable |
| --- | --- | --- | --- | --- |
| 1 | Dependency admission, `make dep-check` | Before a dependency is added | No, it stops the addition | Yes, locally |
| 2 | Pre commit hooks | Before a commit exists | No | Yes, locally |
| 3 | Pre push hooks | Before code leaves the machine | No | Yes, locally |
| 4 | Pipeline scan stage | After build, before deploy | **Yes** | **No** |
| 5 | **Provenance verification** | Immediately before deploy | **Yes** | **No** |
| 6 | Nightly posture scan | Against the running digest | Raises, does not roll back | **No** |

Layers 1 to 3 are convenience. They make the answer arrive in seconds instead
of minutes, and a developer who skips them only defers the same answer to layer
4. That is fine, and it is why they are allowed to be skippable.

**Layer 5 is the admission control for this project**, and it is the one most
projects leave out. Signing an image at build time proves it came from this
pipeline. Verifying that signature immediately before deploy is what makes the
signature useful, because without verification anyone who can push to ECR can
put an unscanned image where the deploy will find it. The verification also
requires an SBOM attestation, and an image with no attestation was never
scanned by this pipeline.

### Why compose is not a gate

A reasonable instinct is to put a scanner in `docker-compose.yml` so nothing
runs unscanned. It does not work, for a structural reason.

**A container cannot gate an image that already exists and is already
running.** By the time a compose service starts, the image is built, on disk,
and startable by anyone with Docker. A scanner service alongside it reports on
a thing that has already happened.

Worse, it produces a false sense of enforcement, which is more dangerous than
no enforcement, because it stops people looking for the real gate.

So the scanners are in a `security` **profile** that does not start with
`make up`:

```bash
make scan-local     # build, then scan with the compose security profile
```

That gives the convenience of scanning locally in one command, without
pretending it is a control. The controls are layers 4, 5 and 6.

### The local loop

```bash
make hooks-install   # once per machine
```

Then, without doing anything else:

- **Every commit**: secrets, writing rules, lint, generated document drift, and
  the dependency admission gate if and only if a manifest changed.
- **Every push**: the full security scan and the test suite.

The manifest condition matters. Scanning the whole transitive tree on every
commit would make committing unbearable and the hook would be disabled within a
week, which is how a security control dies.

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

- Images signed with `cosign`, SBOM attached as an attestation, and **both
  verified immediately before deploy**. Signing without verifying proves
  nothing.
- **Enable ECR enhanced scanning** (Amazon Inspector) on every repository. It
  continuously rescans stored images as new advisories are published, which is
  a registry side backstop for the nightly job. If both are silent, an image is
  genuinely clean rather than merely unscanned.
- ECR repositories set to `IMMUTABLE` tags, so a tag cannot be repointed at a
  different image after it was scanned and signed.
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
| Two principals trusted by name, the task role and the relay, each needing the ExternalId; every role the relay assumes narrowed by a session policy to its one allow listed action | ADR-0035 |
| Every AWS call through endpoints, peered endpoint VPCs and the relay; only the worker may leave the VPC, HTTPS through one NAT gateway to the AI providers' report APIs; held by `tests/contract/test_network_paths.py` | ADR-0028, ADR-0035, ADR-0036 |
| Scope enforced at two independent points | P0 spec section 8, ISS-009 |
| A chosen account only narrows a scope, and one outside it or absent answers the same 404 | FEAT-075 |
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
