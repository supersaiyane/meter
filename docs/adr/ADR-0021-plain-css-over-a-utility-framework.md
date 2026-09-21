# ADR-0021: Plain CSS over a utility framework, against our own tokens

Date: 2026-09-21
Status: Accepted

Supersedes the styling row of ADR-0019. The rest of ADR-0019, headless
behaviour from React Aria, TanStack for the grid, Cytoscape for the graph, and
our own component layer, stands unchanged.

## Context

ADR-0019 decided the component strategy against the interface requirements and
listed four choices. Three were argued in detail. The fourth, "Tailwind with our
tokens for styling", was listed and never argued, and it was never implemented:
no dependency, no admission through `make dep-check`, no configuration.

`ISS-138` recorded what that left. `finops-web/src/tokens.css` declares 27
tokens of which 6 are consumed, defines no layout selector at all, and every one
of the ten screens renders as browser default HTML. The severity ramp is
declared and never applied, so severity reads as repeated squares with no
colour, which defeats the argument in `docs/12-UI-DESIGN.md` section 7 that a
sequential ramp is required because severity is ordered.

Deciding this now, with all ten screens built, means deciding it against the
real surface rather than an imagined one.

## The measurement

| | Tailwind | Plain CSS against the tokens |
| --- | --- | --- |
| Component and screen files touched | 27 | 0 |
| Element instances needing annotation | Roughly 120 | 0 |
| Token handling | Duplicated into a theme, or `bg-[var(--surface)]` | Consumed directly |
| New dependency and configuration | Yes | No |

**No component in this codebase accepts a `className` prop.** There are five
hardcoded class usages in the entire application, and all five are semantic
names like `meter-numeral`. Adopting utilities means either threading a
`className` through every component, which makes the visual layer a caller's
concern, or writing utility strings into every element in 27 files.

## Decision

Plain CSS, in two files, against the tokens that already exist.

| File | Holds |
| --- | --- |
| `finops-web/src/tokens.css` | The tokens, and the classes that carry meaning: provenance fill, numeral, failure, staleness |
| `finops-web/src/layout.css` | Structure, density, surface, border, typography scale, responsive behaviour |

The split follows the document it implements: `docs/12-UI-DESIGN.md` sections 3
and 5 are what a number means, section 7 and section 10 are where things sit.

## Why element selectors are precise here rather than blunt

This is the argument that makes the decision safe, and it would not hold in most
codebases.

`DataTable` is the only table in the product and `Figure` is the only component
that renders a numeral. Across all ten screens there is exactly one `<table>`,
one `<thead>`, one `<th>` and one `<td>` in the source. Styling `th` therefore
styles the one table header that exists, deliberately, rather than reaching
across unrelated components by accident.

That property is a consequence of ADR-0019's own decision to build one thin
component layer, and it is why the framework ADR-0019 reached for is not needed
to get the benefit ADR-0019 wanted.

## Consequences

Positive.

- Zero changes to 27 component and screen files. The visual layer arrives
  without touching behaviour, which means the 168 existing tests continue to
  assert the same things about the same code.
- The tokens are consumed as designed, through `var()`, rather than being
  copied into a second place that can drift from the first.
- No dependency, no admission gate, no build configuration, no purge step that
  can strip a class a test relies on.
- The visual layer is literally ours, which is what ADR-0019 said it wanted.

Negative.

- Element selectors bind the stylesheet to the component layer's markup. If a
  second table is ever introduced outside `DataTable`, it inherits the dense
  treatment whether or not that suits it. The mitigation is the same rule that
  makes this work: one table component, and a review that refuses a second.
- No utility escape hatch for a one off. A one off needs a semantic class and a
  rule, which is slower and is also the point.
- Responsive behaviour is hand written rather than inherited from a framework's
  breakpoints. There are three breakpoints in `docs/12-UI-DESIGN.md` section 10
  and they are written out once.

## Alternatives rejected

**Install Tailwind, as ADR-0019 says.** Rejected on the measurement above. The
cost is 27 files annotated and a theme duplicating tokens, and the benefit,
utilities for rapid composition, is worth least in a product whose central
requirement is a small number of tightly controlled renderings. ADR-0013 rung
two exists to prefer an existing tool, and this is the case where the tool
solves a problem the codebase does not have.

**Plain CSS and leave ADR-0019 unamended.** Rejected. The record and the code
would disagree, which is the drift ADR-0014 exists to prevent, and a reader
would reasonably install Tailwind later on the authority of a document nobody
had corrected.

**CSS modules or a runtime styling library.** Not measured in detail, because
both reintroduce the per component annotation that the measurement above shows
is the actual cost, without removing the need to write the rules.
