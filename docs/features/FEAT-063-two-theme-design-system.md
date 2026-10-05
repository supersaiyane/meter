# FEAT-063: Two theme design system with glass surfaces, dark and light

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | Planned |
| Specification | [P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), section 5.1 |
| Tasks | TASK-P8-001. TASK-P8-013 carries it to every remaining screen |

## What it does

Gives Meter one design system with two themes: Aurora Glass for dark and Frosted Ledger for
light, one set of components over two sets of tokens, kept as plain CSS in
`finops-web/src/tokens.css` under ADR-0021. The theme follows the operating system, and a
toggle overrides it and is remembered per person. With transparency reduced, or on a browser
without `backdrop-filter`, every panel becomes an opaque panel of the same colour and the
page glows are dropped.

## Why it exists

The owner said on 2026-10-05 that the look does not hold attention. After a review of three
directions drawn on the same Overview screen, the owner chose direction A for the dark theme
and direction B for the light theme, as one design system. The look changes, and every rule
that makes the numbers trustworthy survives it.

## What is already known

Glass is a surface, never a reason to lose contrast. Text on glass meets 4.5 to 1 against the
panel at its most transparent over the brightest point of the backdrop, which is why panels
stay at or above the opacities in the spec's token table, and print uses the light theme with
no glass and no glows. One type family serves both themes, Geist for text and Geist Mono for
figures with tabular numerals, self hosted, to be confirmed at approval. The rules in
`docs/12-UI-DESIGN.md` against gradients and against a grid of equal weight cards are amended
with the date and the reason, and its rules on provenance, freshness, absence and numerals stay
word for word.

## Status of this document

Planned. The feature is specified in the
[P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), section 5.1, and planned
as TASK-P8-001 in the [P8 plan](../plans/P8-implementation-plan.md), both pending the owner's
approval. The sections a built feature carries, how it works, its failure behaviour, its
security considerations, its interface and what it does not do, are written when it is built.
Recording only what is decided is deliberate: a document that invents detail ahead of the
build is worse than a short one, because it will be believed.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P8.
