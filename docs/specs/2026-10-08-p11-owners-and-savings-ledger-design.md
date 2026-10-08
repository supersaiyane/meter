# P11 Owners and a savings ledger: design specification

Date: 2026-10-08
Status: Approved by the owner on 2026-10-08, in build. Chosen the same day as the next priority, proposal 3 of `next-in-scope.txt`, answering OPEN-20 for it. OPEN-25 to OPEN-27 were answered as recommended: AWS AppRegistry, CloudTrail's event history, and teams only
Sub project: P11
Features: FEAT-077, FEAT-078, and a change to FEAT-028
Depends on: P3 delivered, for the lifecycle and realized savings, and P4 delivered, for the inventory's tags. Proof against a real estate waits on ISS-002, an AWS account
Supersedes: nothing

## 1. Purpose

An unowned finding is never fixed, ISS-021, the only HIGH issue standing between Meter's findings
and any action on them. And a fixed finding earns its fixer nothing: the State of FinOps 2026
survey names "once you fix it, it's gone" as the problem no tool has solved (as reported by the
survey). P11 gives every finding the owners its estate already names, from the tags, the service
catalogue and CloudTrail, each with its source, and keeps a ledger that credits each verified
saving to the owner and team who made it, re-measured every month it holds.

## 2. Definition of done

- A resource's owners are read from three sources, its tags under the keys a deployment names,
  AWS's service catalogue, and the CloudTrail event that created it, each kept with its source,
  `as_of` and `collected_at`.
- Every recommendation shows those owners as suggestions beside the owner a person assigned,
  strongest first, and a suggestion never becomes an owner without a person accepting it.
- Each saving FEAT-029 verifies is credited to the recommendation's owner and team, with who
  closed it, and re-measured each month afterwards: the months it held and what each saved,
  measured, never projected.
- A ledger screen ranks teams by the savings they hold, labelled measured, and is exportable.
- Every source failing is typed in `sync_error` and never read as "nobody owns this".
- Everything is built and tested against fakes. Reading a real catalogue and real CloudTrail
  waits on ISS-002.

## 3. Out of scope

- Merging two names for one person, a CloudTrail user name and an email, into one owner. It
  needs an identity provider, OPEN-01. Until then an owner is the name a source gave.
- Owners on query findings and anomalies. FEAT-016 keeps them; the same sources serve them
  later, once this sub project has proved them on recommendations.
- A ranking of individuals. OPEN-27.
- Backstage or any catalogue in a code host, which waits on OPEN-13.
- Writing anything to AWS: tags, catalogue entries or trails. Read only, constraint 6.

## 4. The gap, measured on 2026-10-08

Read from the code and the registry on 2026-10-08. Every statement here is measured.

| What | Today |
| --- | --- |
| A recommendation's owner | Free text a person assigns on accepting it, FEAT-028; required from ACCEPTED on |
| A suggested owner | The `team` tag of the inventory node naming the resource, read per request and never stored, CHG-0126 |
| The tag key | One constant, `TEAM_TAG = "team"` in `finops_core/constants.py`; a deployment whose owners live under another key gets no suggestion |
| The service catalogue | Not read |
| A resource's creator | Not read. CloudTrail is read only for query evidence, by event name, `finops_providers/aws/query_evidence.py` |
| Who closed a recommendation | Recorded as the `actor` of each `recommendation_event` |
| A verified saving | One `realized_saving` row per recommendation, cost before and after over two 30 day windows, FEAT-029; credited to nobody, and measured once |

## 5. Decisions

### 5.1 Four sources, one order

A resource can have an owner a person assigned, FEAT-028, and up to three suggested ones:

1. **The service catalogue**: the application a resource is associated with, and the owner its
   attribute group names, section 5.3. Strongest, because somebody wrote it down as ownership.
2. **The tags**: the first of the deployment's owner tag keys the resource carries, section 5.2.
3. **The creator**: the principal of the CloudTrail event that created it, section 5.4. Weakest,
   because whoever created a thing is often not whoever runs it.

A recommendation lists the suggestions in that order, each with its source, under the assigned
owner. A suggestion is never written into `owner`: that stays a person's decision, ISS-021's rule,
and the ledger, section 5.5, credits only an assigned owner.

### 5.2 The tag keys are a setting

`owner_tag_keys` in `Settings`, an ordered list, defaulting to `team` so nothing changes for a
deployment that sets nothing. The first key a resource carries with a non empty value names its
team. A setting rather than a tenant column, because every deployment today holds one tenant;
a second tenant with other keys is the change that moves it into the database. `TEAM_TAG` stays
for the cost allocation it names elsewhere.

### 5.3 The service catalogue is AWS AppRegistry, OPEN-25

AWS Service Catalog AppRegistry, the store behind myApplications: `ListApplications`,
`ListAssociatedResources` for each application's resources, and `ListAttributeGroupsForApplication`
with `GetAttributeGroup` for its attributes, whose JSON holds the owner under the key
`catalogue_owner_key` names, `owner` by default. All four are in the botocore 1.43.108 model
(measured). Recommended because it is AWS's own, read only, and needs no code host. The
alternative, a Backstage catalogue, waits on OPEN-13; a list kept inside Meter is a second
source of truth.

**Amended 2026-10-08 by TASK-P11-003.** AppRegistry does not list an application's resources one
by one: the botocore model's associated resource is a `CFN_STACK` or a `RESOURCE_TAG_VALUE`
(measured), and AppRegistry marks the application's own resources with the tag `awsApplication`,
whose value is the application's ARN, read from `GetApplication`'s `applicationTag`, as AWS
documents it (The awsApplication tag, the AppRegistry guide). So the adapter returns each
application with the tags that mark its resources, `awsApplication` and the
`aws:cloudformation:stack-id` CloudFormation puts on a stack's resources, and the collector
matches the inventory's nodes by the tags they carry. The hub reaches AppRegistry through the
`servicecatalog-appregistry` interface endpoint in every collection Region, which AWS lists among
its PrivateLink services, and the member role gains its five `servicecatalog:` reads.

### 5.4 Creators from CloudTrail's event history, OPEN-26

`LookupEvents` by `ResourceName`, which the botocore model offers as a lookup key (measured),
reading the event that created the resource, through the same paging `query_evidence.py`
already uses. AWS documents its event history as 90 days of management events and its rate as
two requests a second per account and Region; TASK-P11-004 cites the page and holds the
adapter to the rate. A resource created before that window says so, "created before CloudTrail's
90 days", and is never guessed. A creator that is an assumed role session is named as
automation with the role, never as a person, because a pipeline's role is not who to ask.
Recommended over CloudTrail Lake or the organization trail through Athena, which reach further
back but need infrastructure no account has yet, ISS-122; either can replace the adapter behind
the same port.

### 5.5 The ledger credits verified savings to their owner and team

When FEAT-029 records a VERIFIED saving, the ledger writes one credit: the recommendation's owner
when it was marked DONE, the team its strongest team suggestion named then, the actor who moved
it to DONE, and the verified monthly saving, measured. Nothing else is credited: an INCONCLUSIVE
or REGRESSED verdict earns nothing, because the ledger is only worth trusting if nothing in it
is a guess.

**Every month it holds.** At each month's close the resource's cost for that month is read from
`cost_focus_daily` and compared with the cost before the change, at the same daily rate as
FEAT-029's windows. A month where the cost stayed below that is HELD and its saving is added,
measured; a month where it did not is REGRESSED and the credit stops accruing, saying so; a month
with no cost rows for the resource is UNOBSERVED, never nought. A credit's total is the sum of its
held months: what the bill shows the change kept saving, never a figure projected forward.

### 5.6 Who sees the ledger, OPEN-27

Credits are scoped by the account of the resource, as recommendations are, so a reader sees the
credits for what they can see. Recommended: the screen ranks teams; a person's name appears only
as the owner on a team's credits, never in a ranking of individuals, because a leaderboard of
named engineers is a performance review nobody asked Meter to run.

## 6. Data model

Constraint 11: each rule below is a database constraint. Constraint 12: every change is additive.

```
CREATE TABLE resource_owner (            -- one row per resource per source, rewritten each run
    tenant_id, sub_account_id, region_id, resource_id,
    source TEXT in (CATALOGUE, TAG, CREATOR),
    owner TEXT not blank, owner_kind TEXT in (TEAM, PERSON, AUTOMATION),
    detail TEXT not blank,               -- the tag key, the application, or the event id
    as_of, collected_at >= as_of,
    UNIQUE (tenant_id, sub_account_id, resource_id, source)
);

CREATE TABLE savings_credit (            -- one per verified saving
    tenant_id, sub_account_id, recommendation_id, realized_id UNIQUE,
    owner TEXT not blank, team TEXT, closed_by TEXT not blank,
    verified_monthly_saving > 0, verified_on DATE,
    as_of, collected_at >= as_of
);

CREATE TABLE savings_credit_month (      -- each month after verification
    credit_id, month DATE (the first of a month), state in (HELD, REGRESSED, UNOBSERVED),
    cost, saving,                        -- both null exactly when UNOBSERVED; saving > 0 when HELD
    as_of, collected_at >= as_of,
    UNIQUE (credit_id, month)
);
```

All three are scoped by account, the guard's `ByAccount`, constraint 3.

## 7. Collectors and cadence

| Collector | Cadence | Reads | Writes |
| --- | --- | --- | --- |
| `ownership` | Daily | The inventory's tags, no AWS call; AppRegistry per account and Region; CloudTrail only for resources with no creator row yet | `resource_owner` |
| `savings_ledger` | Daily | `realized_saving`, `recommendation_event`, `resource_owner`, `cost_focus_daily` | `savings_credit`, `savings_credit_month` once a month has closed |

Both are rows in `collector_schedule` with their reason, constraint 9. CloudTrail is read once per
resource and never again once a creator or "before the window" is recorded, which keeps the
lookups to the resources created since the last run (modelled).

## 8. Interface

- Recommendations gain `owner_suggestions`: each owner with its kind, source, detail and `as_of`,
  strongest first. `suggested_owner` stays, the strongest team, so no client breaks.
- `GET /savings/ledger`: teams by the savings they hold, with credits, months held and the
  latest month, exportable.
- `GET /savings/ledger/credits`: one team's credits, each with its months, exportable.
- The recommendations screen lists the suggestions with their sources under the owner cell.
- A Savings ledger screen under Optimize, its figures labelled measured.

## 9. Testing

- Each source on its planted case: a resource tagged under a second key, one in an application
  with an owner, one created by a person, one by a pipeline's role, one older than 90 days.
- A source that fails is typed in `sync_error` and leaves the other sources' rows standing.
- A suggestion never writes `owner`.
- Only a VERIFIED saving is credited; a month that regressed stops the accrual; a month with no
  cost is UNOBSERVED and never a zero.
- A reader narrowed to one account sees only that account's credits.
- Against the seeded demo, every DONE and VERIFIED recommendation has exactly one credit.

## 10. Risks

| Risk | Mitigation |
| --- | --- |
| A creator is a pipeline, not a person | Named as automation with its role, never a person, section 5.4 |
| One person under two names | Kept apart and said so until OPEN-01; out of scope, section 3 |
| A ledger used to rank people | Teams only, OPEN-27 |
| A cost that falls for another reason | The month shows usage beside cost, as FEAT-029 does, and credits only VERIFIED changes |
| CloudTrail's rate | Once per resource, never again, and held to the documented rate in the adapter |

## 11. Open questions

| ID | Question | Recommended |
| --- | --- | --- |
| OPEN-25 | Which service catalogue | AWS AppRegistry, section 5.3 |
| OPEN-26 | CloudTrail event history, or Lake or the organization trail | Event history first, section 5.4 |
| OPEN-27 | May the ledger rank individuals | No, teams only, section 5.6 |

## 12. Features delivered

- FEAT-077 Owners from tags, the service catalogue and CloudTrail.
- FEAT-078 The savings ledger, verified savings credited and re-measured.
- FEAT-028 gains the suggestions beside the assigned owner.

## 13. Exit criteria

1. Every source is read on its planted case, and a failing one is typed and stands alone.
2. Every recommendation shows its suggestions with their sources, and none is ever written as an
   owner.
3. Every verified saving in the seeded demo has one credit naming an owner, a team where one is
   known, and who closed it.
4. Every credit's months are HELD, REGRESSED or UNOBSERVED, measured, and none is a zero for a
   month nobody observed.
5. The ledger ranks teams, never individuals, within the reader's scope, and is exportable.
