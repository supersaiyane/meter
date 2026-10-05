# FEAT-063: Two theme design system with glass surfaces, dark and light

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | In progress |
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
figures with tabular numerals, self hosted, confirmed by the owner on 2026-10-05. The rules in
`docs/12-UI-DESIGN.md` against gradients and against a grid of equal weight cards are amended
with the date and the reason, and its rules on provenance, freshness, absence and numerals stay
word for word.

## How it works

`finops-web/src/tokens.css` names every colour once, light and dark together, through
`light-dark()`, so `color-scheme` alone chooses the theme. The operating system sets it until a
person chooses. `src/theme.ts` pins a choice as `data-theme` on the root element and remembers
it, and `src/shell/ThemeToggle.tsx` offers System, Light and Dark at the foot of the navigation.
The three lengths that differ by theme, a panel's radius, blur and saturation, are declared
once for a system that prefers dark and once for a person who chose it, and a test holds the two
equal. A panel is the `.meter-panel` class: the translucent `--surface-raised`, a hairline, a
one pixel inner highlight and a backdrop blur, all from tokens. The page carries three radial
glows, one per corner, and the shell's main column is transparent so the glows reach the panels.

## Failure behaviour

With transparency reduced, or on a browser without `backdrop-filter`, `--surface-raised` and
`--surface-raised-2` become their opaque `-solid` equivalents, the colour the glass would have
shown over the bare page, and the glows are dropped. Print is the light theme with neither. A
browser that refuses storage keeps the theme on the operating system's choice, because
`src/storage.ts` treats a refusal as no value.

## Security considerations

Geist and Geist Mono are served from `node_modules` through the bundle, admitted through
`make dep-check` with zero findings, so a page showing spend makes no request to a font host.
The only value stored is the word `system`, `light` or `dark`.

## Interface

The tokens in `tokens.css`, the `.meter-panel` class, `storedTheme`, `applyTheme` and
`chooseTheme` in `src/theme.ts`, and the `ThemeToggle` component.

## Not doing

It does not restyle the screens: the tokens apply everywhere at once, and TASK-P8-013 moves each
screen onto glass panels. The choice is remembered in the person's browser, not across their
devices. Two light values differ from the spec's table, for its own contrast rule: faint is
`#5a687d`, and the accent drawn as text is `#0064d2`, with the table's `#0a84ff` kept as the
accent mark. `docs/12-UI-DESIGN.md` section 7 gives the ratios.

## Status of this document

In progress. TASK-P8-001 built the design system on 2026-10-05, and TASK-P8-013 carries it to
every remaining screen.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P8.
