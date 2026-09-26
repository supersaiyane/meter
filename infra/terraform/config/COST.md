# What this stack costs, and the working

TASK-P4-010's second acceptance criterion: the task carries the estimated monthly cost,
with the resource type count and the assumed configuration item volume that produced it.
A number with no working is not an estimate.

**Every figure on this page is modelled. None is measured.** No recorder has ever run,
which ISS-203 records, so there is nothing to compare with yet. The mechanism for finding
out is the platform cost screen: constraint 7 tags every resource here
`finops:module = config`, so the real bill appears beside this estimate rather than in a
console somebody has to go and look at.

The arithmetic also lives in `cost.tf` as locals, so a plan prints the number and a diff
that changes the type list or the region list moves it where a reviewer sees it.

## The estimate

| Quantity | Value | Measured or modelled |
| --- | --- | --- |
| Resource types recorded | 22 | Counted from `resource_types.tf` |
| Accounts | 300 | Modelled, the scale this project targets |
| Regions with a recorder | 2 | From `var.recorder_regions`, which is the cost lever |
| Active account and region slices | 600 | Derived |
| Recorded resources per slice | 200 | Modelled |
| Configuration items per resource per month | 4 | Modelled, and the least certain figure here |
| Configuration items per month | 480,000 | Derived |
| Price per configuration item | 0.003 USD | Modelled from the published price list |
| **Estimated monthly cost** | **1,440 USD** | **Modelled** |

## Why each assumption is what it is

**Twenty two types.** Counted from the three groups in `resource_types.tf`, each of which
names the feature that needs it. Fourteen for FEAT-031's network graph, six for FEAT-027
and FEAT-028's waste findings, two global ones for the cross account trust edges. A type
with no feature behind it is a type to remove, and the file lists the four deliberately
excluded ones with the reason for each.

**Two hundred resources per slice.** A VPC, three subnets, a handful of security groups,
the instances and volumes behind one application, and the network interfaces those imply.
The network interface count dominates, which is why `AWS::EC2::NetworkInterface` is in the
list explicitly rather than assumed away: it is the type most likely to make this estimate
wrong, and leaving it out of the model would make the estimate look better than the bill.

**Four configuration items per resource per month.** One for the resource existing when
recording starts, plus three changes. This is the least certain number on the page. A
stable estate is nearer one; an estate with autoscaling groups cycling instances hourly is
very much more, and `AWS::AutoScaling::AutoScalingGroup` being in the list means those
cycles are recorded. If the real figure is ten rather than four, the estimate is 3,600 USD
rather than 1,440, and that is the direction the error runs in.

**Two regions.** `var.recorder_regions` defaults to two, and it is the single largest
lever on this page: eleven regions is five and a half times the number above. A region
with no recorder has no configuration items, and its `graph_coverage` row stays `UNREAD`
rather than `COMPLETE` with nothing in it, which is the distinction P4 exists to keep.

## The decision this stack is

ISS-012 says organization wide Config recording is a five figure monthly line item.
Recording every supported type across the same estate is modelled at roughly six times
the number above, about **8,600 USD a month**, on the assumption that everything an
account holds is about six times the twenty two types Meter reads. That is the number
selective recording avoids, and it is why `AllSupported` is `false` in `recorder.yaml`
with the reason written beside it rather than left as a default.

Selective recording was decided on 2026-09-20. ISS-012 is decided, not closed: whether
this estimate survives contact with a real estate is unknown, and the way to find out is
to apply the stack in one account, read the platform cost screen, and come back here.

## What would change this page

- A resource type added to `resource_types.tf`. Add its marginal cost here in the same
  change, because the type list is the only reviewable record of the decision.
- A region added to `var.recorder_regions`. Multiply.
- A measured figure from a real recorder. Replace the modelled row and say which it is.
