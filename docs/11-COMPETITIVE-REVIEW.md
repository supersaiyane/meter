# Competitive review

Last updated: 2026-08-23
Update trigger: any review of a comparable product
Method: read the vendor's own claims, take what is better than ours, record
what we reject and why

A living document. One dated section per review. Reports are not edited after
they are written, in the same way audit reports are not, because the value is
in knowing what was believed at a point in time.

---

## 2026-08-23: NudgeBee AI FinOps

Source: `https://nudgebee.com/ai-finops`, read 2026-08-23. Claims are the
vendor's own and are not independently verified.

### What it validated

Worth recording, because convergence on a decision by an independent team is
evidence the decision is not eccentric.

| Their position | Ours |
| --- | --- |
| "510 rules and the FinOps Score run deterministically." Finding and ranking uses zero language model tokens | ADR-0007, almost word for word |
| Normalises first party savings from Compute Optimizer, Cost Optimization Hub, Cost Explorer, Trusted Advisor, Azure Advisor, GCP Recommender | ADR-0006 |
| STS AssumeRole with an ExternalId, no long lived credentials | ADR-0004 |
| OpenCost in the customer's own cluster for allocation | P6, FEAT-036 |
| Every change requires human approval, pull requests against GitHub or GitLab | FEAT-040 |
| Publishes the full working: parameters, formulas, data windows | Our measured versus modelled rule |
| Self hosted, zero telemetry, billing data queried in place | Our single tenant deployment, inherently |

### What we took

| Their capability | Became | Why it is better than what we had |
| --- | --- | --- |
| Severity by dollar impact, High at 100 USD a month, Medium at 20 | ADR-0016 | Ours was a chosen label, so the ranking reflected the author rather than the impact |
| Anomaly detection requiring Z score 3.0 **and** 50 USD absolute **and** 20 percent relative, on a 30 day clean baseline, auto resolving after two normal days | FEAT-023 amended | Ours had no thresholds at all. Requiring all three concurrently is the specific thing that stops anomaly detection becoming noise and being muted |
| Auto-Pilot scores blast radius from the dependency graph and auto applies only safe changes | FEAT-044 | The best idea on their page. We already build that graph in FEAT-031 and did nothing with it beyond drawing it |
| Outbound AI requests scanned for secrets, redact or block | FEAT-046 | We have seven scanners and none looked at what leaves for Bedrock |
| CSV and Excel export for chargeback and showback | FEAT-045 | Finance does not live in our interface. A FinOps tool that cannot hand finance a file is missing its actual consumer |
| Cluster node fleet optimisation as an integer linear program | FEAT-047 | Ours stopped at reporting bin packing efficiency. Theirs solves it |
| FinOps Score, 0 to 100, recalculated every 6 hours | FEAT-043 | Adopted with a condition, see below |
| LSTM replica forecasting, 24 steps to a 168 step horizon | FEAT-048, ADR-0015 | Adopted with four conditions, see below |
| Memory at peak plus 15 percent, or 25 percent after an OOMKill. 50 data points over 2 weeks | FEAT-036 amended | OOMKill awareness is a genuinely good detail we did not have |
| Abandoned workload detection over a 7 day window, persistent volume growth forecasting | FEAT-036 amended | Cheap additions to a collector we were already building |

### Two adopted against my recommendation, and how

Both were adopted on the project owner's decision after I argued against them.
Recorded plainly, because a decision taken over an objection should be
findable later along with what the objection was.

**The FinOps Score.** My objection: a single composite number is good for a
sales page and bad for an engineering team, because nobody can tell what moved
it or what to do about it.

The objection becomes a design constraint rather than being dropped. FEAT-043
ships only if **the score decomposes**. Every score shows its components,
every component links to the findings that moved it, and a change in the score
between two runs is explainable as a list of findings that opened or closed. A
score that cannot be taken apart is not shipped.

**LSTM replica forecasting.** My objection: it introduces a trained model into
a product whose credibility rests on every number being reproducible and
defensible.

ADR-0015 answers it by drawing the actual line. A forecaster may produce a
number because it is reproducible, backtestable, has a stated error bound, and
fails visibly when inputs drift. A language model has none of those properties.
Four conditions apply: published backtest accuracy, an error bound on every
forecast, a deterministic fallback to the p95 rule, and a third provenance
label `forecast` alongside `measured` and `modelled`.

### What we rejected

| Their capability | Why not |
| --- | --- |
| Cloud API remediation, writing directly to AWS, Azure and GCP | We are read only in v1, and that is load bearing in the threat model: it is why a compromised hub role gives reconnaissance rather than control. A legitimate v2 conversation, not something to adopt by copying |
| Live Kubernetes patching of deployments | Same reason. A write path into a customer cluster is a different security posture and needs its own threat model |
| A rule count as a headline, 510 rules across four clouds | A count is a marketing number. Two hundred rules nobody acts on is worse than twenty that get fixed. We track realized savings instead |
| 78 integrations | Not a capability, a surface area. Each one is a maintenance liability and a supply chain entry |

### What they have that we deliberately will not

They ship a free community edition, paid tiers, and a four assistant platform
including AI SRE and CloudOps. Meter is an internal platform for one
organization. Product packaging is not a gap.

### Honest position

They are ahead of us in three places: remediation paths, cluster level
optimisation maths, and breadth of first party integration. They are behind on
one thing that matters here, and it is the thing this project exists for:
**nothing on their page addresses observability query cost governance**, which
is the failure that cost 100,000 USD in a week and started this work.

That remains the differentiator, and it is worth noticing that a mature
commercial product in this exact category does not cover it.

---

## 2026-09-26: IBM Turbonomic

Sources, all read 2026-09-26. Every capability below is the vendor's own claim or a
secondary report of it, and none is independently verified, exactly as in the section
above.

- `https://www.ibm.com/products/turbonomic`
- `https://www.ibm.com/products/turbonomic/cloud-optimization`
- `https://www.ibm.com/products/turbonomic/dashboards`
- `https://www.ibm.com/docs/en/tarm/8.20.0?topic=notes-whats-new`, the 8.21.0 release
- `https://www.ibm.com/new/announcements/introducing-top-action-in-ibm-turbonomic-smarter-cloud-optimization-starts-here`
- `https://www.ibm.com/new/announcements/ibm-turbonomic-and-ibm-kubecost-unite-to-optimize-kubernetes-performance-and-cost`
- `https://www.finout.io/blog/ibm-turbonomic-solution-overview`
- `https://www.peerspot.com/products/ibm-turbonomic-pros-and-cons`
- `https://ibm.github.io/waiops-tech-jam/labs/turbonomic/ui-and-k8s-data-target-lab/ui/`

### Read this before the tables

**We are not near them, and the honest answer to the question is a number.** Meter has
14 of 51 features delivered, measured from `docs/registry.yaml` on 2026-09-26, is at P4
of eight sub projects, and no part of it has ever made a call to an AWS account, ISS-122.
Turbonomic is a product that has been sold since 2010, was acquired by IBM in 2021, and
in its 8.21.0 release added support for Oracle Cloud Infrastructure, IBM Cloud migration
planning, Azure Databricks, Google H3 and Z3 instance families, Hyper-V 2025, Nutanix VM
categories, OpenStack 18 and Linux on IBM Z.

So this section is a direction finder rather than a scorecard. The useful output is the
list of things they do that we have not thought about, not a percentage.

### What Turbonomic is, in one idea

Everything else follows from this. Turbonomic models the estate as **a market**. Every
entity, from a business application down through transactions, services, containers,
pods, virtual machines, hosts and datastores, is both a buyer and a seller in a supply
chain. Resources carry a price in a virtual currency, and rising demand raises the price,
which is how contention is signalled. A **risk index** derived from those prices
anticipates a performance problem instead of waiting for a static threshold to trip.
Actions fall out of the market clearing rather than out of a rule list.

That is a fundamentally different starting point from ours. Meter starts from the bill and
works towards the resource. Turbonomic starts from demand and works towards both
performance and the bill. Neither is wrong, and the difference explains most of the gaps
below.

### Where we are behind, worst first

**1. It acts. We only report.**

Their product is execution: pod and container scaling, VM placement and resizing,
workload parking, resource rebalancing, capacity reclamation, GPU allocation, and in
8.21.0 a single action that deletes an idle VM together with its attached volumes on all
three major clouds. Actions can be set to execute automatically under policy, with an
audit trail.

Meter is read only in v1 and constraint 6 makes that load bearing: it is why a compromised
hub role gives reconnaissance rather than control, per `docs/08-THREAT-MODEL.md`. Our
remediation path is a generated infrastructure as code pull request, FEAT-040, which is
planned and not built.

This is a deliberate difference, not an oversight, and it is still the largest gap,
because the consequence is real: their savings happen and ours wait for a person. The only
honest way to close the distance without changing the security posture is FEAT-040 plus
FEAT-029, realized savings, which is the one metric that would show whether recommendations
ever turn into money. FEAT-029 is delivered; FEAT-040 is not.

**2. They optimise for performance. We have no performance dimension at all.**

Turbonomic's stated purpose is performance assurance: keeping workloads inside their
service level objectives by preventing contention, and in 8.21.0 an SLO Guard that scales
Kubernetes services horizontally against a user defined response time target using Instana
metrics.

Meter never asserts that a workload is **underprovisioned**. Our rightsizing in
`finops_query/waste.py` uses p99 CPU and observed memory peak specifically to avoid
recommending a harmful shrink, and ISS-195 added a memory bound refusal for exactly that
reason. But avoiding harm is not the same as protecting performance, and a tool that only
ever recommends making things smaller is one engineers learn to discount. This is the most
important gap that is not obvious from a feature list, and nothing in P5, P6 or P7
addresses it.

**3. Their dependency model reaches the application. Ours stops at infrastructure.**

Their supply chain runs business application, business transaction, service, application
component, container, pod, node, virtual machine, host, datastore, and the front page is a
picture of it.

P4 delivered our graph on 2026-09-26: 14 node kinds and 7 edge kinds, all infrastructure.
There is no application layer, no business transaction, and no link to an APM tool. We can
answer which account and which tag a cost belongs to. We cannot answer which business
application it belongs to, which is the question an executive actually asks.

**4. What if planning. We have none.**

Their Plan view simulates a migration, a hardware change or an added workload before any
of it happens, and 8.21.0 added vCenter to OpenShift Virtualization and vCenter to IBM
Cloud migration plans.

We have `finops_query/cost_model.py`, which computes a modelled cost with no IO and no
clock, and no surface that lets anybody ask a scenario question. ADR-0015 already permits a
deterministic forecast, so the door is open and nothing has walked through it.

**5. Commitment and discount handling is much deeper.**

They ingest negotiated rates, show a discount inventory with coverage and utilisation
charts, handle reserved instances, savings plans, Azure SQL Managed Instance reservations
and Google flexible committed use discounts, and, the part that matters,
**generate scaling actions whose purpose is to raise discount coverage**.

FEAT-024, delivered in P1, reports commitment use and coverage payer wide and stops. We
say what the coverage is. They change it.

**6. Parking. We have no scheduling primitive.**

Policy driven stop and start of idle workloads on a schedule, with smart parking that picks
the moment from utilisation trends, plus an Overview tab for effectiveness, a workload
details panel with parking history, and a parking history tab.

Meter has nothing here, and in most real estates a non production fleet stopped outside
office hours is the single largest and least risky saving available. We do not look at it.

**7. Breadth of target.**

AWS, Azure, Google Cloud, Oracle Cloud Infrastructure, IBM Cloud, VMware, Hyper V,
Nutanix, OpenStack, Kubernetes and OpenShift. Ours is AWS, with `finops_providers/gcp`
and `azure` reserved as directories and not written.

Constraint 1 means adding one is a connector rather than a rewrite, which is the right
shape, and it is still one against eleven.

**8. Kubernetes depth.**

An in cluster agent, Kubeturbo, with namespace quota resize automation, out of memory
remediation, eviction of unresponsive pods, Argo Rollouts support, volume aware pod
placement that respects per node Container Storage Interface attachment limits, a Prometheus
setup wizard, an admission controller, and one click agent updates. The Kubecost and OpenCost
integration reached public preview on 2025-12-01 and shows current against predicted cost per
resize action.

Our P6 is five features, all specified, none started.

**9. Infrastructure as code, and they arrived where we did.**

Their IaC integration is generally available: Terraform configuration and state discovery
across GitHub, GitLab and Azure DevOps, with remote state in S3, Azure Blob Storage or
Google Cloud Storage. They also import HashiCorp Sentinel policies and generate automation
policies from them.

This is worth recording as validation rather than only as a gap. FEAT-040 chose the same
answer, a pull request against the customer's own repository, and an independent team with
far more resources chose it too. What they have and we do not is the discovery half: reading
the Terraform state so an action knows which file to change.

**10. Operational maturity we have not begun.**

Custom roles with granular permissions, RBACv2, in public preview. OAuth 2.0 client
management, in public preview. Air gapped telemetry export. One click agent updates. Linux
on IBM Z. Our authorization is three tiers, viewer, analyst and owner, and a scope, which
is enough for one organization and would not survive a second tenant asking for a custom
role.

### The interface, screen by screen

This is the part the question asked about separately, and the gaps are different in kind:
most of them are surfaces we have not built rather than things we built badly.

**What they show**

| Their screen | What is on it |
| --- | --- |
| Home | The Supply Chain graphic, the whole stack at once, entities coloured red for a performance risk, yellow for an efficiency opportunity and green for nothing to do. Widgets for Top Business Applications, Top Business Transactions, Top Services, Pending Actions and Risks Avoided |
| Top Actions | On the Cloud home page. The five highest impact actions per category, ranked, with the low risk ones flagged as executable immediately. Categories are performance and cost saving |
| Action Center | Global. Every optimisation opportunity in one place, viewable, executable, or set to automate |
| Application map | Entities grouped by application, with each application's pending actions |
| Search and Groups | Find any entity, build a group, scope a policy or a dashboard to it |
| Plan | What if. Simulate a migration, a hardware change or an added workload |
| Policies | Automation policies and schedules, including parking policies |
| Dashboards | Cloud Executive, On Prem Executive, Container Platform, and custom dashboards scoped per team |
| Optimisation views | Cloud Compute, Cloud Storage, Database, Discounts, and Workload Parking, the last with Overview, Workload details and Parking history tabs |
| Entity detail | One resource, its metrics, its Entity Information chart, and in 8.21.0 its IPv4, IPv6 and MAC addresses |
| Settings | Target configuration, users, roles |

**What we show.** Nineteen of twenty four screens across the seven fixed navigation groups
ADR-0020 settled, counted from the `arrives` field in `finops-web/src/shell/sections.ts`:
Home, Cost with five screens, Waste with three, Governance with five, Inventory with four,
Platform with three, Assistant with two.

**Where our interface is behind**

| Gap | Detail |
| --- | --- |
| No action centre | Our `/waste` lists recommendations with a lifecycle and an owner, which is more than they have on ownership, but there is no single place that holds every opportunity and no way to execute one. That follows from being read only |
| No ranked start here surface | Their Top Actions says do these five. We have severity derived from money, ADR-0016, and a decomposable FinOps Score, FEAT-043, and no widget that answers what should I do this morning. Our home is a trust strip and the platform's own cost. This is the cheapest of these gaps to close and probably the most valuable |
| No whole estate picture | Our topology map is a neighbourhood around one chosen root, bounded to four hops and two thousand nodes. Theirs is the entire supply chain, on the front page, always. Ours is the better answer for a large estate and the worse answer for orientation, and we have nothing for orientation |
| No what if screen | Nothing at all |
| No custom dashboards | Every screen of ours is fixed. That is ADR-0020 on purpose, because a dashboard builder nobody maintains becomes forty stale dashboards, and it is still true that a team cannot make its own view |
| No per entity detail page | We have a finding detail screen. We have no page that says here is this instance, its metrics, its history and what we think about it |
| No resource list | Their Search and entity views list anything. Reviewing this surfaced ISS-204: the navigation already promises an `/inventory/resources` screen arriving with P4, and the P4 specification never scheduled one, so a delivered sub project is named as the thing that will bring it. The data exists, because `topology_node` carries the region and zone FEAT-030 was built for |
| No executive view | The FinOps Score is the closest thing we have, and it decomposes where theirs is a headline number. What we lack is the one page a director reads |

**Where our interface is ahead, and their own users say so**

| Ours | Their reported problem |
| --- | --- |
| Every number carries its provenance, measured, modelled or forecast, FEAT-050 and ADR-0015, and a number reaches a user only through `Figure` | Users report "aggressive or noisy recommendations requiring manual validation", which is the symptom of a product that does not publish its working |
| Coverage is a persistent, non dismissible statement counting the right unit, and `degraded` is computed and never set | Users report reports that "won't provide much information if we dig down further than the application layer" |
| Failures are typed to six causes with remediation text, and a failure is never rendered as a zero | Not addressed in anything read |
| P4 added a third state: a slice that was never read is UNREAD, not empty, and a traversal refuses to answer a question needing completeness | Not addressed in anything read. This is the one design idea in Meter with no counterpart on their side |
| Zero axe violations and keyboard reach asserted per screen, at 1080p | Users report a web interface that "assumes high resolution displays", with 1080p users scrolling through cramped windows, and a UI that is "overwhelming and complex" with "dense dashboards" |

The last row is worth dwelling on. The most common complaint about Turbonomic's interface
is that there is too much of it. Our seven fixed groups and our refusal to ship a dashboard
builder are the same problem solved in advance, and we should not treat their screen count
as a target.

### Where we are still ahead

**Observability query cost governance.** Searching their product pages, their 8.21.0
release notes and their documentation for CloudWatch Logs Insights cost, Grafana dashboard
refresh governance or query cost control returns nothing. Grafana Cloud does this for its
own product and Vantage integrates with them for it; Turbonomic does not appear to address
it at all.

That is the failure that started this project: a Grafana dashboard against CloudWatch Logs
Insights on a one second refresh over a seven day window, 100,000 USD in a week, no control,
no alert and no owner. P2 delivered five of the eight routes for it and the enforcement path
is parked on ISS-122.

Two mature commercial products in this category have now been reviewed and neither covers
it. That is the clearest signal yet that the differentiator is real rather than a gap we
have talked ourselves into liking.

**Ownership and workflow.** FEAT-028 gives a recommendation an owner, a ticket reference and
a lifecycle with a terminal state, and ISS-021 is the reason: an unowned finding is never
fixed. Nothing read suggests Turbonomic attaches a named human to an action.

**Refusing to answer.** `finops_query.graph.Subgraph.require_whole` refuses over a partial
or unread slice rather than scoring what it can see. A product built on an economic model
that always clears has no natural place to put that refusal.

### What we deliberately will not take

| Their capability | Why not |
| --- | --- |
| Direct write execution into member accounts and clusters | Constraint 6, and the threat model depends on it. A legitimate v2 conversation with its own threat model, not something to adopt by copying |
| Breadth of target as a goal | Eleven platforms is eleven maintenance liabilities. One cloud done properly, with constraint 1 keeping the second cheap, is the right shape for one organization |
| A dashboard builder | ADR-0020. Their own users complain about interface sprawl, which is what a builder produces |
| A single headline efficiency number | Already settled by FEAT-043's ship condition: a score that cannot be decomposed is not shipped |

### What is worth taking, not yet registered

Proposals, deliberately not written into `docs/registry.yaml`, because adopting a feature
is the project owner's decision and the section above this one records what happened last
time that was done by inference.

| Candidate | Why | Size |
| --- | --- | --- |
| A ranked start here surface on the home screen, five actions, with the low risk ones marked | The largest value for the least work in this list. Everything it needs exists: severity from money, the FinOps Score's components, and the recommendation lifecycle | Small |
| A performance dimension, so the product can say underprovisioned and not only oversized | The gap that most damages trust with engineers. Needs a headroom rule and a service level input, and it changes what the waste collectors mean | Large |
| Workload parking, as a finding first and a schedule later | The biggest untouched saving in most estates, and a finding version needs no write path | Medium |
| Commitment coverage actions rather than commitment coverage reporting | We already hold the data. What is missing is turning a coverage gap into a ranked recommendation | Medium |
| A per entity detail page | Cheap, and the obvious destination for every link on every list we already have | Small |
| Terraform state discovery, so FEAT-040 knows which file to change | FEAT-040 cannot produce a useful pull request without it, and their generally available version is evidence the approach works | Medium |
| An application layer on the topology graph | Would let us answer which business application a cost belongs to. Needs a tag convention or an APM target, and it is the honest prerequisite for an executive view | Large |

### Honest position, 2026-09-26

They are ahead on execution, on performance, on planning, on commitment optimisation, on
platform breadth, on Kubernetes depth and on operational maturity. That is most of the
product surface, and the gap is measured in years rather than in features.

We are ahead on three things, and each of them is a property of the design rather than a
feature that could be copied quickly: every figure states whether it was measured or
modelled, incompleteness is a first class state that consumers must handle, and a finding
has a named owner and a terminal state. Plus the one capability neither reviewed competitor
has at all, which is the reason this project exists.

The useful conclusion is not that we should try to catch up. It is that the two smallest
items in the table above, a ranked start here surface and a per entity detail page, would
close the most visible part of the interface gap, and that the performance dimension is the
one large thing worth arguing about before P5 starts.
