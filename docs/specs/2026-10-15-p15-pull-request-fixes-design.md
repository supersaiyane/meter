# P15 Fixes through pull requests: design specification

Date: 2026-10-15
Status: Approved by the owner on 2026-10-15 with OPEN-13 and OPEN-41 to OPEN-43 answered, in build. Chosen the same day as the next priority, proposal 4 of `next-in-scope.txt`
Sub project: P15
Features: FEAT-091, FEAT-092, FEAT-093, FEAT-094, and FEAT-040 finished
Depends on: P3 for recommendations and their lifecycle, P4 for FEAT-057's map of what Terraform manages, P7 for FEAT-040's authoring, P9 for FEAT-074's gp2 to gp3 rule, P12 for the composition every new collector joins, P13 for ADR-0036's worker only route to the internet. Proof against a real repository waits on a GitHub App installation
Supersedes: FEAT-040's rule that a fix is never merged. ADR-0038 records the change

## 1. Purpose

Meter finds waste and says what to do about it, and then a person has to do it. FEAT-040 already
writes the fix for eight kinds of waste as a Terraform change, but nothing sends it anywhere: there
is no code host behind the port, OPEN-13, so no pull request has ever been opened, ISS-228. And the
fix it writes is always a deletion, so even a perfect pull request waits for a person who has to be
sure nothing still needs the resource.

P15 delivers the fixes. A person asks Meter to fix a recommendation, and Meter opens a pull request
in the repository whose Terraform manages the resource, through a GitHub App the organization
installs. It adds a fix that loses nothing if it is wrong, a volume moved from gp2 to gp3, which is
an edit to the file that declares the volume. And under a policy the tenant turns on, Meter merges
such a fix itself once the repository's own required checks and reviews have passed. A deletion
always waits for a person. Meter still never applies anything: the organization's own pipeline
applies what is merged, and constraint 6 holds, no write into a member account.

## 2. Definition of done

- A tenant connects a GitHub App installation, naming the app, the installation and the Secrets
  Manager name of its key, and maps each Terraform state file Meter reads to a repository, a base
  branch and a folder. Both are made by a person whose scope is the organization, and audited.
- A person whose scope includes a recommendation's account asks for a fix, and Meter opens a pull
  request in the mapped repository for any of the eight removals and for gp2 to gp3, or says why it
  cannot. Asked twice, it opens one pull request, not two.
- gp2 to gp3 is an edit to the file that declares the volume, found by reading the mapped folder:
  the type set to gp3, and IOPS and throughput set where FEAT-074's rule needs more than gp3 gives.
  A volume whose type is not a plain value in one file is refused with the reason.
- Meter follows each pull request it opened: open, merged by whom, or closed without merging, each
  a recorded step. A merged fix is not a done one: the recommendation is done when the inventory
  sees the change, and FEAT-029 verifies the saving from the bill sixty days later.
- With the tenant's policy turned on for gp2 to gp3, Meter merges such a pull request once GitHub
  says it is mergeable with every required check passed and every required review given. It never
  merges a deletion, whatever the policy says, and with the policy off it merges nothing.
- The app's key never leaves Secrets Manager except as a token minted for one request, valid for an
  hour at most, and only the worker reaches GitHub, ADR-0036.

## 3. Out of scope

- Applying anything. The organization's pipeline applies what is merged. Constraint 6.
- Approving a pull request, or merging past a repository's protections. Meter merges only what
  GitHub already says may be merged.
- GitLab, Bitbucket, CloudFormation and Grafana panel patches. The port takes another host when one
  is asked for.
- Resizing an instance, OPEN-43. It touches running workloads and is left to a later sub project.
- Deleting the resource's own block in a removal. FEAT-040's removal file still tells the reviewer
  to delete it, and a deletion always waits for that person.

## 4. The gap, measured on 2026-10-15

| What | Today | Measured or modelled |
| --- | --- | --- |
| Pull requests Meter has opened | 0; the port has a fake and no adapter, ISS-228 | Measured, from the code |
| Recommendation classes a fix is written for | 8 of 20, every one a deletion | Measured, from `finops_query/remediation.py` |
| Classes whose fix loses nothing if wrong | 0 written; gp2 to gp3 is priced by FEAT-074 and never authored | Measured, from the code |
| Merges Meter may make | 0; `tests/contract/test_no_llm_writes.py` refuses the word | Measured, from the test |
| Code hosts Meter can reach | None; the worker alone reaches the internet, on 443, ADR-0036 | Measured, from the Terraform |

## 5. Decisions

### 5.1 GitHub, through a GitHub App, OPEN-13

The organization installs a GitHub App on the repositories that hold its Terraform, granting
Contents and Pull requests, read and write, and Checks, Commit statuses and Metadata, read. The
app's private key is stored in the hub account under `meter/<env>/codehost/`, a path only the
worker's task role may read, as P13's provider keys are. For each request the worker signs a ten
minute JSON Web Token with the key, exchanges it for an installation token valid for an hour, and
uses that alone; no token is stored. Answered by the owner on 2026-10-15: a GitHub App.

### 5.2 Meter merges a reversible fix under the tenant's policy, OPEN-41

A class of fix is reversible when undoing it loses nothing: gp2 to gp3 changes a volume's type in
place, and a second change moves it back. Only reversible classes may ever be merged by Meter, and
the set is in the domain, not in configuration: `EBS_GP2_TO_GP3` alone in P15. A tenant's merge
policy lists which reversible classes Meter may merge, starts empty, and is changed by a person
whose scope is the organization, with a reason, audited. A database check refuses a policy naming
any class outside the reversible set, so a deletion cannot be turned on by any path.

Meter merges a pull request it opened, of a class the policy names, only when GitHub reports it
mergeable, every required status check passed and every required review given. It merges through
GitHub's own merge, so branch protection still applies, and records the merge as a step with the
policy that allowed it. A feature flag, `pull_request_merge`, turns every merge off at once. ADR-0038
records the change to FEAT-040's rule. Answered by the owner on 2026-10-15: reversible fixes only.

### 5.3 The repository comes from a mapping the owner sets, OPEN-42

FEAT-057 records, for each resource Terraform manages, its address and the state file that owns
it. The tenant maps each state file to a repository, a base branch and a folder, so the fix for a
resource goes to the folder whose Terraform wrote that state. A resource with no mapping, or no
`resource_management` row, gets no pull request, and the screen says which is missing. Answered by
the owner on 2026-10-15: a mapping the owner sets.

### 5.4 The first cut writes removals and gp2 to gp3, OPEN-43

The eight removals are authored as FEAT-040 already writes them. gp2 to gp3 is new: the worker
lists the mapped folder's `.tf` files, reads them, and finds the one `resource "aws_ebs_volume"
"<name>"` block the address names. The edit sets `type = "gp3"` and, where FEAT-074's rule needs
more than gp3's included 3,000 IOPS or 125 MiB/s, `iops` and `throughput`. The edit is pure text
arithmetic in `finops_query`, tested without GitHub. It refuses, with the reason, a type set by a
variable or an expression, a resource inside a module, an address with an instance key, a block
found in no file or in more than one, and a volume FEAT-074 says gp3 cannot match. Answered by the
owner on 2026-10-15: removals plus gp2 to gp3.

### 5.5 The API records, the worker acts

Only the worker reaches the internet, ADR-0036, so a request to open a pull request is a row the
API writes, and the `fix_pull_requests` collector opens it, follows it and, under the policy,
merges it. The collector runs every ten minutes, a cadence in `collector_schedule` like every
other, so a person who asks sees the pull request within ten minutes and every later step within
the next run.

### 5.6 Merged is not done

A merge changes the repository; the organization's pipeline changes the account. So a recommendation
whose pull request is open or merged is `IN_PROGRESS`, and becomes `DONE` when the inventory sees
the change: the resource gone for a removal, the volume's type gp3 for an edit. FEAT-029 then
measures the saving from the bill sixty days after, as for any recommendation marked done. A pull
request closed without merging returns the recommendation to `ACCEPTED`, with the step recorded.

## 6. Data model

New tables, each with `as_of` and `collected_at`, constraint 10:

- `code_host_connection`: one row per tenant, the host, the app's id, the installation's id, the
  Secrets Manager name of the key, never a value, who connected it and when. A check holds the name
  to `meter/<env>/codehost/`. `PayerWide`, ADR-0025.
- `repository_mapping`: one row per tenant and state file, the repository, the base branch and the
  folder, who set it and when. `PayerWide`.
- `fix_pull_request`: one per recommendation asked to be fixed, its status, `REQUESTED`, `OPEN`,
  `MERGED`, `CLOSED`, `NOT_AUTHORED` or `FAILED`, the repository, the branch, the host's number and
  link, who asked and when, who merged, and a failure's typed cause. A unique index allows one live
  pull request per recommendation. Scoped as the recommendation's account is.
- `fix_pull_request_event`: each step, with its principal, a person, Meter, or the host's login of
  whoever merged or closed it, and the time.
- `merge_policy`: one row per tenant and class Meter may merge, the reason, who set it and when. A
  check holds the class to the reversible set. `PayerWide`.

## 7. Collectors and cadence

| Collector | Unit | Cadence | Reads and writes |
| --- | --- | --- | --- |
| `fix_pull_requests` | organization | every 10 minutes | Opens each requested pull request, follows each open one, merges under the policy, and marks a recommendation done when the inventory sees its change |

It joins the registry, both compositions, the fakes, and a migration installing its cadence for
existing tenants. It costs nothing at AWS: GitHub's API is free within its rate limit, and the
worker's NAT carries kilobytes, modelled.

## 8. Interface

- `GET` and `PUT /v1/remediation/connection`: the GitHub App installation. Global scope.
- `GET` and `PUT /v1/remediation/repositories`: the mapping of state files to repositories. Global
  scope.
- `GET` and `PUT /v1/remediation/merge-policy`: which reversible classes Meter may merge, with a
  reason. Global scope.
- `POST /v1/waste/recommendations/{id}/pull-request`: ask for a fix, with a note. A person whose
  scope includes the recommendation's account.
- `GET /v1/remediation/pull-requests`: every fix asked for, its status and its steps.
- The recommendation's detail page gains the fix: ask for it, its pull request, its steps, and why
  where there is none. A settings screen gains the connection, the mapping and the merge policy.

Every response carries `as_of` and `collected_at`, constraint 10. The MCP facade gains the read
routes only, ADR-0009.

## 9. Testing

The GitHub adapter is tested against recorded response shapes through httpx's mock transport, for
every typed failure: a refused token, a repository the app is not installed on, a branch that
exists, a rate limit, and a host that does not answer. The gp2 to gp3 edit is tested without a
database on real Terraform text, including each refusal. The merge rule is tested for every
combination of policy, class, mergeability, checks and reviews, and a contract test fails the gate
if any module other than the one merge function names a merge, or if any module approves, applies
or starts a tool that changes a cloud. The routes are tested for a narrowed principal refused where
the organization's scope is needed. The screens have unit tests and a Playwright journey.

## 10. Risks

- Nothing is proven against a real repository until an app is installed. Every GitHub shape is
  recorded from GitHub's published REST reference.
- An organization whose pipeline applies on merge gives Meter a path to a change in an account. That
  is the point of the policy and why it starts empty, covers reversible fixes only, and merges only
  through the repository's own protections.
- Terraform written by hand varies. The edit refuses whatever it cannot read for certain, and says
  why, rather than writing a change that may not plan.
- A rate limit stops a run part way. Each pull request is its own step, so a run that stops leaves
  every other one as it was.

## 11. Open questions

OPEN-13 and OPEN-41 to OPEN-43, all answered by the owner on 2026-10-15, sections 5.1 to 5.4.

## 12. Features delivered

- FEAT-040: Remediation authoring as an infrastructure as code pull request, finished: opened for
  real.
- FEAT-091: The code host connection and the repository mapping.
- FEAT-092: A fix asked for, opened as a pull request, and followed until the inventory sees it.
- FEAT-093: gp2 to gp3 written as an edit to the file that declares the volume.
- FEAT-094: Meter merges a reversible fix under the tenant's merge policy.

## 13. Exit criteria

1. A removal asked for on a mapped, managed resource opens one pull request in the mapped
   repository, and asking again opens no second one.
2. A gp2 to gp3 asked for opens an edit to the file that declares the volume, and a volume whose
   type is set by a variable is refused with the reason.
3. With the policy on for gp2 to gp3, a mergeable pull request with its checks passed and reviews
   given is merged by Meter and recorded; with the policy off, or for a deletion, nothing is merged.
4. A merged fix leaves the recommendation in progress until the inventory sees the change, then
   done, and FEAT-029 verifies it.
5. The app's key is read only by the worker, only from `meter/<env>/codehost/`, and no token is
   stored; only the worker reaches GitHub.
6. The screens let a person ask for a fix and see its steps, and let a person whose scope is the
   organization connect the app, map the repositories and set the policy; a narrowed person is
   refused where the organization's scope is needed.
