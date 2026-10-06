# FEAT-052: Top actions, ranked, with what each change costs if it is wrong

| Field | Value |
| --- | --- |
| Sub project | P3 |
| Status | Delivered |
| Specification | [competitive review](../11-COMPETITIVE-REVIEW.md), 2026-09-26 section |
| Tasks | None. Small enough to land as one change, on the owner's decision of 2026-09-26 |
| Refresh cadence | Follows FEAT-028. The panel owns no query |
| Source | Adopted from the IBM Turbonomic review on 2026-09-26 |

## What it does

Two things, and the second is the reason the first is worth having.

A panel on the home screen answering what to do this morning: the five biggest savings that
are still open, and the five that can be undone without stopping anything. Ranked by money,
per ADR-0016, in the same order the recommendations screen uses.

And a risk statement on every recommendation, everywhere it appears: whether the change is
reversible, whether applying it disturbs running work, and a sentence saying why.

## Why it exists

Meter had severity derived from money and a decomposable posture score, and no answer to
"what should I do first". The Turbonomic review recorded that as the cheapest of the seven
gaps to close and probably the most valuable, because everything it needs already existed.

Their Top Actions widget flags the actions a reader can apply immediately with minimal risk.
We cannot copy that flag: Meter applies nothing, constraint 6. What transfers is the
judgement underneath it, and building that judgement turned out to be the substance of this
feature rather than the panel.

## What is already known

**Risk is two questions and neither is confidence.** A high confidence rightsizing still
needs a restart. A low confidence snapshot deletion is still permanent. `confidence` comes
from the length of the observation window and says nothing about either, so a single blended
number would be wrong in both directions.

**Most changes that disturb nothing are still permanent.** Of the eighteen waste classes,
eight disturb no running work and only three of those eight can be undone. The three a reader
is most likely to apply without thinking are among the five that cannot: releasing an
unassociated Elastic IP, deleting an unattached volume, and setting a retention period on a
log group that has none. Releasing an address means the same address is never reissued and
anything allow listing it fails afterwards. Setting a retention period deletes everything
already older than it, immediately.

That is why the label leads with the word permanent rather than with the absence of
disruption. A surface calling those three low risk because nothing was running would be
reassuring about exactly the wrong findings.

## How it works

`finops_query/actions.py` holds a closed table from `WasteClass` to
`Risk(reversible, disturbs_running_work, why)`. `is_no_regret` is derived, and needs both
halves. The table is total over the enumeration and a test asserts it, so a waste class added
to the domain fails the build rather than reaching a screen with no risk statement: every
default available at that point is a lie in one direction or the other.

The three flags and the sentence ride on `RecommendationOut`, so every consumer of the
existing route gets them and there is no second route to keep in step. They are computed from
the class rather than stored on the row, because the risk of a class is a property of the
class: storing it would need a migration every time a sentence was improved, and eighteen
copies of a sentence is eighteen chances for one to be the old one.

`components/TopActions.tsx` rolls up from `useRecommendations`, which is the recommendations
screen's own hook and its own query key. The home screen owns no query, per
`docs/13-UI-ARCHITECTURE.md`: a panel with its own query will one day disagree with the
screen it summarises, and a reader who catches that stops trusting both.

The wording lives in `components/actionRisk.ts` rather than beside the panel, because the
entity detail page shows the same label against the same findings and a second copy would be
a second answer to how dangerous a change is.

Since TASK-P8-013, 2026-10-06, each group's table is a `DataTable`: still ranked by money first and now sortable by any column, so its header row shows. No total, because a group can hold two findings on one resource that are alternatives.

## Failure behaviour

An empty group says so in words rather than rendering blank, because a blank panel reads as
broken and an empty group is a claim about the estate.

The no regret group is short by design and is sometimes empty. Three classes of eighteen
qualify, and a page of easy wins would be inventing most of them.

The panel summarises the rows the recommendations hook returned, which is at most two hundred
ordered by saving. A small reversible finding beyond that limit does not appear. That is the
cost of owning no query and it is the right trade: a dedicated query would have found those
rows and would also have been the second answer this page exists to avoid.

There is no performance group, and the panel says so on the page. Meter judges what is
oversized and never what is starved, which the competitive review records as the largest gap
that is not obvious from a feature list. A reader is entitled to know the two groups are not
the whole picture.

## Security considerations

Nothing new. The panel reads the recommendations route, which is already scoped by the
request dependency and the repository guard, so a narrowed reader sees a ranking over the
accounts they can read and no others. The risk table holds no tenant data and no identifiers.

Nothing here can be applied, which is constraint 6 and is why the label says what a change
would cost rather than offering to make it.

## Interface

`/`, tier two, above the query findings table. Two panels in that tier since 2026-09-26, and
the order is the claim: top actions answers what to do across the whole estate and the
findings table is the same question narrowed to query governance.

Every row carries the label and the sentence. The label is what a reader scans, the sentence
is what they decide on, and a label with no sentence behind it is one nobody can argue with.
Savings render through `Figure` as modelled, never measured.

## Not doing

Applying anything. Constraint 6, and FEAT-040's generated pull request is the path.

Boosting no regret findings up the money ranking. The two groups are separate rather than
blended, so the biggest saving list is exactly the biggest saving list and a reader comparing
it with the recommendations screen sees the same order. A blended rank would have been a
third ordering nobody could reproduce.

A performance category. That needs a headroom rule and a service level input, and it changes
what the waste collectors mean. The competitive review sizes it as large and it is the one
worth arguing about before P5 starts.
