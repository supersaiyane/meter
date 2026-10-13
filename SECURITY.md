# Security

<!-- Basic boiler Plate Doc | Grade A
     Why this file exists: The public statement of how to report a vulnerability.
     Grade A here: nothing in this file is specific to this project. Copy it unchanged.
     Grades: A copy into a new project as is, no edits. B copy it and swap the
     names, paths or patterns named above. C leave behind, it is this project's
     own content rather than scaffolding, and is not tagged.
-->

## Reporting a vulnerability

Report privately. Do not open a public issue, and do not include a working
exploit in the first message.

| | |
| --- | --- |
| Contact | `PLACEHOLDER-security@example.com` |
| Response | Acknowledgement within 2 business days |
| Assessment | Severity and a remediation window within 5 business days |

Please include what you found, how to reproduce it, and the impact you believe
it has. If you are unsure whether something is a vulnerability, report it
anyway.

## Scope

Meter holds, for an entire AWS Organization: account identifiers, the
organization structure, cost data at resource granularity, resource inventory,
and the ability to assume a read only role in every member account.

Anything affecting the confidentiality of that data, the integrity of the
figures it reports, or the boundary between one principal's scope and another's,
is in scope. So is anything that lets an unscanned or unsigned image reach a
deploy.

## Our posture

The full policy is `docs/05-SECURITY.md`. In short:

- **Zero vulnerabilities at any severity.** Not zero critical, not zero high.
- Six enforcement layers, of which three cannot be skipped: the pipeline scan,
  provenance verification before deploy, and a nightly scan of the digest that
  is actually running.
- Every dependency passes an admission gate scanning its whole transitive tree
  before it is added.
- Exceptions are time boxed, carry a named owner, expire within 90 days, and
  break the build when they expire.
- Read only into member accounts. No write API call. Remediation is delivered
  as a generated infrastructure as code merge request.

Scan reports and the current posture are committed under `security/`, so the
position at any date is reconstructable.

## What we ask

Give us a reasonable window to fix an issue before disclosing it. We will keep
you informed, and we will credit you unless you prefer otherwise.
