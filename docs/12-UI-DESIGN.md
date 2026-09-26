# User interface design

Last updated: 2026-08-23
Update trigger: any new screen, any new data state, any change to the provenance language
Applies to: every sub project, P0 to P7
Closes: the gap found on 2026-08-23, that the product's honesty guarantees were undesigned

## 1. The problem this document exists to solve

The data model has 90 lines of constraints making a wrong value impossible to
store. The interface had 18 lines naming five screens.

That asymmetry is not a documentation problem. It is a design problem, because
**every honesty guarantee in this product is a visual guarantee**:

| The guarantee | Where it is enforced | Where it is kept |
| --- | --- | --- |
| A figure is `measured`, `modelled` or `forecast` | A check constraint | **A pixel** |
| Data was true at `as_of`, fetched at `collected_at` | Two `NOT NULL` columns | **A pixel** |
| A failed collection is not the number zero | A closed error taxonomy | **A pixel** |
| A total covers 42 of 310 accounts | `scope_coverage` on every response | **A pixel** |
| A run `PARTIAL` is not a run `SUCCEEDED` | A check constraint | **A pixel** |

A constraint stops bad data being stored. Nothing stops a screen presenting
good data misleadingly. The database work is worthless if the last six inches
throw it away.

## 2. Frame

| | |
| --- | --- |
| **Purpose** | Let a person trust a number enough to change infrastructure |
| **Audience** | Platform engineers, FinOps practitioners, engineering directors, finance. Financial services |
| **Tone** | An instrument, not a dashboard. Sober, dense, unshowy |
| **Direction** | **Industrial**. A good measuring device: a laboratory instrument or an oscilloscope, not a marketing surface |
| **The one thing a user should remember** | **You can always tell how much a number is worth trusting.** |

That last line is the design thesis. Every decision below is downstream of it,
and a decision that does not serve it is decoration.

### What the direction rules out

No hero sections. No gradient fields. No card grids of equal weight. No
celebratory colour. No decorative motion. No illustration.

A tool that reports a 100,000 USD mistake should not look pleased with itself.

## 3. Provenance: the primary visual axis

Provenance is not metadata shown on hover. **It is the first thing the eye
resolves about any figure**, ranking above the figure's own magnitude.

### Three states, encoded redundantly

Never by colour alone. Colour fails for roughly 8 percent of men, fails in
print, fails in a screenshot pasted into a ticket, and fails in a board pack
photocopied twice.

| State | Fill | Numeral | Marker | Meaning |
| --- | --- | --- | --- | --- |
| `measured` | Solid | Full weight | none | Observed. Real execution counts, real bytes |
| `modelled` | **Diagonal hatch** | Full weight | `~` prefix | Projected. Ranks reliably, does not reconcile to the bill |
| `forecast` | **Hatch plus interval whiskers** | Range, not a point | `~` prefix and an interval | Predicted. Carries an error bound, ADR-0015 |

The hatch is inherited deliberately: the existing Grafana audit prototype
already draws modelled bars hatched, and the people who will use this have
already learned that vocabulary. Continuity beats novelty.

**A forecast never renders as a single number.** `6 to 9 replicas` and never
`7 replicas`. ADR-0015 condition 2 is a rendering rule as much as a data rule.

### The accuracy figure travels with the label

Where a calibration exists, FEAT-018, the modelled label carries it:
`~ $12,400 modelled, +/- 9%`. Where it does not, the label says
`accuracy not yet published`, which is worse looking and more honest.

## 4. Freshness: two timestamps, never one

Every screen showing a figure shows **how old the data is**, not when the page
loaded.

```
as of 04:00 today            data was true at the source then
collected 6 min ago          Meter fetched it then
```

Rules.

1. **Never "just now" or "live".** Meter is never live. CUR refreshes at most
   three times a day and Cost Explorer is roughly a day behind.
2. **Age, not a timestamp**, for `collected_at`. "6 min ago" is read
   correctly; "11:04:22Z" requires arithmetic.
3. **Absolute for `as_of`.** "as of 04:00 today" is a claim about the world and
   must be precise.
4. **Staleness is computed against the collector's configured cadence**, not a
   fixed threshold. A daily collector six hours old is fine. An hourly one six
   hours old is not.

### Three freshness states

| State | Treatment |
| --- | --- |
| Current | Neutral. No emphasis. Freshness is present but quiet |
| **Stale** | Amber rule above the figure, and the age becomes prominent |
| **Unknown** | The figure is **suppressed**. See section 5 |

## 5. The rule that matters most: a failure is never a number

**A cell whose collection failed does not render a numeral. Ever.**

Not zero. Not a dash. Not an em dash, which is banned anyway. Not blank.

It renders the **typed cause** and a way to act:

```
  Account            Cost            Provenance
  111122223333       $4,201.55       measured
  444455556666       $312.10         ~ modelled
  777788889999       ACCESS DENIED   collector role not assumable  [fix]
  222233334444       $0.00           measured
```

The fourth row is a genuine zero and reads as one. The third does not compete
with it. That distinction is the entire product.

### Every typed error has a fixed rendering

| Cause | Label | Action offered |
| --- | --- | --- |
| `AccessDenied` | ACCESS DENIED | The remediation, and a recheck |
| `Throttled` | THROTTLED | Retrying, with the next attempt |
| `NotOptedIn` | NOT ENABLED | The enablement step |
| `NoData` | `0` or empty | **None. This is the only cause that renders as a number** |
| `Unreachable` | UNREACHABLE | The network cause |
| `SchemaDrift` | UNRECOGNISED | The raised issue |

### Totals in a column containing failures

A column total is **never** the sum of what happened to succeed.

```
  Total (297 of 300 accounts)      $184,203.11
  3 accounts could not be read     [show]
```

The denominator is part of the number. A total that silently omits three
accounts is a confident lie, and it is the failure this whole design exists to
prevent.

## 6. Scope coverage: persistent, never a toast

A user seeing 42 of 310 accounts must never be able to forget it.

- **Persistent in the shell**, not a dismissible banner. A banner gets
  dismissed; the condition does not go away.
- Complete coverage says so: `showing all 310 accounts`. Absence of a warning
  is not confirmation, and users need confirmation.
- **Every export carries it.** A spreadsheet that leaves the product without
  its coverage becomes a number in a board pack with no way back to what it
  meant. FEAT-045.
- Out of scope branches in the organization tree are **drawn and marked
  unreachable**, never pruned. A tree with unexplained gaps reads as broken
  data and destroys trust in the parts that are correct.
- **Made once per page, not once per panel.** Four summary tiles reading one
  partially collected estate each repeated the same sentence, and announced it
  four times to a screen reader, which buries a claim rather than making it.
  `StateBoundary` takes `coverageShownElsewhere` for exactly this: it drops the
  sentence and never the rows, and it is only correct where the shell above
  already carries the claim. A surface that sets it and shows coverage nowhere
  is a defect, which is what the test beside it exists to catch.

## 7. Visual system

### Typography

Two faces, chosen for function.

| Role | Face | Why |
| --- | --- | --- |
| **All numerals** | A monospace with tabular figures. JetBrains Mono or IBM Plex Mono | Costs are compared vertically. Proportional digits make `$1,204.10` and `$984.22` impossible to scan. This is not taste |
| Prose, labels, navigation | A humanist sans. Inter or IBM Plex Sans | Reads well at small sizes, wide weight range, unfashionable in a good way |

Numerals are **always** tabular, **always** right aligned, and a currency
column always shows the same number of decimal places, including trailing
zeros. `$0.00`, never `$0`.

**Decided, 2026-09-24: IBM Plex Sans and IBM Plex Mono, self hosted.** The
table above offered alternatives and `tokens.css` shipped neither, using
`system-ui` instead. A system stack renders a different face per operating
system, so column widths and density differ between two people reading the same
figures, which is not acceptable for a screen whose whole job is comparing
numbers down a column. The faces are served from `node_modules` through the
bundle, latin subset only, so a page showing customer spend makes no request to
a third party font host.

Scale: 12, 14, 16, 20, 28, 40. Six sizes. A seventh means the hierarchy is
unclear rather than insufficient.

### Colour

One dominant neutral field, selective accent. Colour never carries meaning
alone.

| Token | Use |
| --- | --- |
| `--surface`, `--surface-raised`, `--line` | The field. Almost everything |
| `--ink`, `--ink-muted` | Text |
| `--accent` | Interactive only. Not decoration |
| `--stale` | Amber. Freshness only |
| `--fail` | Red. Typed failures only, never a low number |
| `--sev-1` to `--sev-4` | Severity, a **sequential ramp**, not a rainbow |

Severity is sequential because severity is ordered. A categorical palette for
an ordered quantity makes `HIGH` and `MEDIUM` look like different kinds of
thing rather than different amounts.

**The ramp is warm, decided 2026-09-24.** It used to be blue, and its darkest
step was the same value as `--accent`, `#1f4f8f`, in light and in dark. The most
severe finding was therefore painted the one colour that means "this is a link"
everywhere else, which contradicts the rule two rows above that the accent is
interactive only. A warm ramp is squeezed between the failure red and the
staleness amber and sits about twenty degrees of hue from each, which is the
most separation available; the redundant square glyph and the word in the chip
are what actually carry the level, and the fill only ranks it. The ordering is
enforced by `contrast.test.ts`, which asserts the ramp descends by luminance
rather than merely differing, and the two darkest steps carry text so they are
also held to 4.5 to 1.

**Red is never used for "expensive".** A large number is not an error. Red is
reserved for a failure, so that when it appears it means one thing.

Light and dark are both first class. The instrument reads in a bright office
and in a dark incident bridge.

### Spacing and density

A 4 px rhythm. Density is a deliberate choice per surface:

| Surface | Density | Why |
| --- | --- | --- |
| Tables, inventories, findings | **Dense**. 32 px rows | The user is scanning hundreds of rows for outliers |
| A single finding, a recommendation | **Generous** | The user is making a judgement, and needs room to read the evidence |
| The shell | Compact | It is chrome, not content |

Dense is not cramped. Dense means no wasted vertical space, with alignment
doing the work padding would otherwise do.

### Surface and border

Borders, not shadows. Shadows imply elevation and physicality, which suits a
consumer application and not an instrument. One `--line` value, used
consistently, is enough to build every boundary in the product.

### Motion

**Almost none, and one deliberate exception.**

Permitted: a 120 ms opacity transition on state change, and a skeleton while
loading. That is the list.

Forbidden: entrance animations, number count-ups, hover lifts, page
transitions, anything decorative.

A number that animates from 0 to 4,201 is *lying for 400 milliseconds*, and in
a product whose entire claim is that its numbers are trustworthy, that is not a
small thing.

The one exception: **when a figure changes because data refreshed**, the cell
marks briefly. Not to delight. To tell a user reading a screen that the ground
moved under them.

## 8. State matrix

Every data surface implements all seven. A screen that implements five is not
finished.

| State | Rendering | The mistake to avoid |
| --- | --- | --- |
| **Loading** | Skeleton at the true final dimensions | A spinner, which hides how much is coming |
| **Empty, genuine** | "No accounts match this filter", with the filter shown | Looking identical to a failure |
| **Empty, never collected** | "Not yet collected", with the collector's next run | Rendering as an empty success |
| **Partial** | Data, plus a persistent count of what is missing and why | Showing the successful rows only |
| **Stale** | Data, with the age raised in prominence | Silence |
| **Degraded** | Data, plus which collector is failing | A generic error toast |
| **Failed** | The typed cause and its remediation | A numeral. Any numeral |

## 9. Accessibility

Not a later pass. Two of these are load bearing for the product's core claim.

- **WCAG 2.2 AA**, and AAA contrast on numerals, because misreading a digit is
  the failure mode that matters here.
- **Provenance is never colour alone.** Hatch, prefix and label carry it
  independently. This is in section 3 as a product requirement and repeated
  here as an accessibility one, because it is both.
- **Full keyboard operation**, including the organization tree. The tree is
  the default view over the graph partly for this reason.
- **The graph view has a non graph equivalent.** A force directed layout is not
  accessible to a screen reader, so the tree is the accessible path and is
  never the secondary one.
- Focus visible always. Reduced motion respected, which given section 7 costs
  us almost nothing.
- Every error announced to assistive technology, with its typed cause.

## 10. Responsive

Desktop first, honestly. This is an analyst's tool used on a large screen, and
pretending otherwise produces a bad desktop experience in exchange for a mobile
one nobody wants.

| Width | Behaviour |
| --- | --- |
| 1280 and above | Full density, all columns |
| 1024 to 1280 | Secondary columns collapse behind a disclosure |
| Below 1024 | **Read only summary.** Coverage, freshness, top findings. No editing, no graph |

Below 1024 is a phone checking a number during an incident. It needs the
figure, its provenance and its age. It does not need the whole instrument.

## 11. Component inventory

Built once, in P0, used by every sub project. A sub project inventing its own
table is how a product acquires four table styles.

| Component | Notes |
| --- | --- |
| `DataTable` | Dense, sortable, virtualised past 200 rows, tabular numerals |
| `Figure` | **The most important component.** A number plus its provenance, freshness and failure states. Nothing renders a number directly |
| `CoverageBanner` | Persistent, shell level |
| `FreshnessIndicator` | Age plus `as_of`, staleness against cadence |
| `TypedError` | Cause, remediation, action |
| `SeverityBadge` | Sequential ramp, label and shape |
| `OrgTree` | Keyboard navigable, marks unreachable branches |
| `GraphCanvas` | Cytoscape, server filtered, with the tree as its accessible equivalent |
| `Sparkline` | 30 day, no axes, provenance aware |
| `StateBoundary` | Wraps a surface, implements all seven states from section 8 |

**`Figure` is the load bearing one.** No screen formats a number itself. If a
number can only reach a user through a component that requires its provenance,
then a screen that forgets provenance cannot be built. That is the same
technique as the repository scope guard: make the wrong thing impossible rather
than discouraged.

## 12. Library choice, decided against these requirements

Deferred deliberately until the requirements existed, then decided here.

| Requirement from above | Consequence |
| --- | --- |
| Bespoke provenance, freshness and failure rendering | A component library's table would be fought, not used |
| Dense virtualised tables | Needs a real virtualiser, not a styled `<table>` |
| Full keyboard operation of a tree | Accessible tree behaviour is subtle and expensive to hand write |
| WCAG 2.2 AA, AAA on numerals | Behaviour and focus management must be correct by default |
| One visual language we control | The visual layer must be ours |

**Decision: headless behaviour, our own visual layer.**

- **Radix Primitives** or **React Aria** for behaviour and accessibility.
- **TanStack Table** and **TanStack Virtual** for the data grid.
- **Plain CSS** against our tokens for styling, per ADR-0021. Tailwind was the original choice here and was superseded once the measurement existed: no component in this codebase accepts a `className`, so utilities would have meant annotating 27 files to avoid writing one stylesheet.
- **Cytoscape.js** for the graph, as already decided.
- Our own thin component layer implementing section 11.

This is ADR-0013 rung five, composition. Rung two, an existing component
library, is disqualified on evidence rather than taste: the product's central
requirement is a bespoke rendering of every number, and the components a
library gives you are precisely the ones we must control. Rung seven, building
accessible tree and focus management from scratch, is disqualified because it
is a large amount of subtle work that is not this product's problem.

Recorded as ADR-0019, with the styling row superseded by ADR-0021.

## 13. What this does not cover

- P2 to P7 screen designs. Each sub project specification adds its screens
  against this system rather than inventing one.
- Brand, logo, marketing. Meter is an internal instrument.
- Charting beyond the sparkline. P1 introduces charts and must extend section 7
  with a chart specific provenance treatment before it does.
