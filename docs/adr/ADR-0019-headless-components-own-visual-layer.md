# ADR-0019: Headless component behaviour, our own visual layer

Date: 2026-08-23
Status: Accepted

## Context

The frontend needs components. The choice was deliberately deferred until the
interface requirements existed, because choosing a library first and then
discovering it fights the requirement is the expensive order.

`docs/12-UI-DESIGN.md` established those requirements, and one of them
dominates: **every number in this product must carry its provenance,
freshness and failure state**, and a number must not be renderable without
them.

## Decision

Headless libraries for behaviour and accessibility. Our own visual layer.

| Concern | Choice |
| --- | --- |
| Behaviour, focus, keyboard, ARIA | Radix Primitives or React Aria |
| Data grid, virtualisation | TanStack Table, TanStack Virtual |
| Styling | Tailwind, driven by our tokens |
| Graph | Cytoscape.js, already decided |
| Components | Our own thin layer, the inventory in section 11 |

## Consequences

Positive.

- Accessible tree, menu and focus behaviour arrives correct. It is subtle,
  expensive to hand write, and not this product's problem.
- The visual language stays ours, which matters because the provenance and
  freshness treatment is the product rather than a theme.
- `Figure` can be made the only path a number takes to a screen, so a screen
  that forgets provenance cannot be built. The same technique as the repository
  scope guard: make the wrong thing impossible rather than discouraged.

Negative.

- More initial work than adopting a full library. A styled table exists on day
  one with Mantine and does not here.
- We own the visual layer, so we own its consistency. The component inventory
  and `StateBoundary` exist to bound that.
- Two dependency families, headless behaviour and TanStack, each needing to
  pass the admission gate.

## Alternatives rejected

**A full component library, Mantine or MUI.** Rung two of ADR-0013, and
disqualified on evidence rather than taste. The requirement is a bespoke
rendering of every number, every empty state and every failure. The components
such a library provides are exactly the ones we must control, so we would spend
the saved time fighting them, and end up with a product whose most important
visual decision is inherited from a general purpose kit.

**Build everything, including behaviour.** Rung seven. Accessible tree
navigation, focus trapping, and roving tabindex are a large amount of subtle
work with well maintained implementations available. ADR-0013 forbids climbing
to rung seven without disqualifying the lower rungs, and rung five is not
disqualified.

**Defer again, decide during implementation.** Rejected. The choice is now
made against written requirements. Deciding it inside a task means deciding it
under time pressure, which is how a product acquires a library nobody chose.
