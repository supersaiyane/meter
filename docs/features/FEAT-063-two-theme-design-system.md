# FEAT-063: Two theme design system with glass surfaces, dark and light

| Field | Value |
| --- | --- |
| Sub project | P8 |
| Status | In progress |
| Specification | [P8 spec](../specs/2026-10-05-p8-experience-and-reporting-design.md), section 5.1 |
| Tasks | TASK-P8-001 and TASK-P8-018. TASK-P8-013 carries it to every remaining screen |

## What it does

Gives Meter one design system with two themes: Aurora Glass for dark and Frosted Ledger for
light, one set of components over two sets of tokens, kept as plain CSS in
`finops-web/src/tokens.css` under ADR-0021. Light opens for a reader who has chosen
nothing, by the owner's decision later on 2026-10-05; a toggle in the toolbar offers System,
Light and Dark and is remembered per person. The rail is a glass panel in both themes, and
motion is rich and never on a figure. With transparency reduced, or on a browser
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
`light-dark()`, so `color-scheme` alone chooses the theme. Light holds until a person chooses:
`index.html` pins it before any script runs, so a dark system never flashes a dark page, and
`src/theme.ts` pins a choice as `data-theme` on the root element and remembers it.
`src/shell/ThemeToggle.tsx` offers System, Light and Dark in the toolbar of every screen.
The three lengths that differ by theme, a panel's radius, blur and saturation, are declared
once for a system that prefers dark and once for a person who chose it, and a test holds the two
equal. A panel is the `.meter-panel` class: the translucent `--surface-raised`, a hairline, a
one pixel inner highlight and a backdrop blur, all from tokens. The blur is itself one token,
`--panel-filter`, declared in `:root` alone so no theme block outranks a fallback, and every
glass surface blurs through it: the panel, the rail and the trust strip. `glass.test.ts` holds
that for every stylesheet. The page carries three radial
glows, one per corner, and the shell's main column is transparent so the glows reach the panels.

Motion is drawn from tokens too, TASK-P8-018: `--motion-fast` for controls, `--motion-base`
for the cross fade between screens, `--motion-slow` for panels rising in a few at a time, and
`--motion-chart` for a time series drawing in left to right, all on one easing. A panel lifts
under the pointer with `--shadow-lift` unless it holds a table, and a menu floats with
`--shadow-float`; at rest a panel still separates by its hairline. The keyframes are a named
set of five and none animates a size, so no number counts up and no bar grows from zero.

The shell holds at every width. `finops-web/e2e/viewports.spec.ts` sweeps every screen the
rail links to at 320, 375, 768, 1024, 1280 and 1920 pixels, with the rail open and hidden, and
fails if a screen scrolls sideways or is not given the width the shell leaves it. It reads the
screens off the rail, so a screen added later is swept without being listed.

Since TASK-P8-013, 2026-10-06, no colour is named outside `tokens.css`, held by a test that
reads the layout and every component's source: the brand mark's two stops, the one literal
left, became `--brand-from` and `--brand-to`, with one value in either theme so the mark stays
the same. `e2e/a11y.spec.ts` runs axe over every screen's own content, read off the rail and
opened over the demo estate, in light and in dark, as well as over the shell. It found one
fault on two screens, a table wider than its box that no keyboard could scroll, so a table that
scrolls is now a keyboard stop named by its caption, and one that fits adds nothing to the tab
order.

## Failure behaviour

With transparency reduced, or on a browser without `backdrop-filter`, `--surface-raised` and
`--surface-raised-2` become their opaque `-solid` equivalents, the colour the glass would have
shown over the bare page, `--panel-filter` becomes `none` so nothing is blurred, and the glows
are dropped. Until TASK-P8-014 the fallbacks switched the panel's blur off by name and left the
rail and the trust strip blurred, ISS-257. `finops-web/e2e/a11y.spec.ts` opens every screen on
the rail in both themes with transparency reduced, and again as a browser without
`backdrop-filter` reads the shipped stylesheet, and holds each opaque, unblurred and axe clean.
It also holds that no screen draws glass inside a table or a list. Print is the light theme
with none of it. A
browser that refuses storage keeps the light default, because `src/storage.ts` treats a
refusal as no value. A reader who asks for reduced motion gets none: nothing fades, rises,
draws, pops or lifts. The journeys run that way so they read the settled screen, and
`finops-web/e2e/motion.spec.ts` proves both states from the computed animation.

## Security considerations

Geist and Geist Mono are served from `node_modules` through the bundle, admitted through
`make dep-check` with zero findings, so a page showing spend makes no request to a font host.
The only value stored is the word `system`, `light` or `dark`.

## Interface

The tokens in `tokens.css`, motion and shadow among them, the `.meter-panel` class,
`DEFAULT_THEME`, `storedTheme`, `applyTheme` and `chooseTheme` in `src/theme.ts`, and the
`ThemeToggle` component.

## Not doing

It does not restyle the screens: the tokens apply everywhere at once, and TASK-P8-013 moves each
screen onto glass panels. The choice is remembered in the person's browser, not across their
devices. Two light values differ from the spec's table, for its own contrast rule: faint is
`#5a687d`, and the accent drawn as text is `#0064d2`, with the table's `#0a84ff` kept as the
accent mark. `docs/12-UI-DESIGN.md` section 7 gives the ratios.

## Status of this document

In progress. TASK-P8-001 built the design system on 2026-10-05, TASK-P8-018 made light the
default, drew the rail and the top bar and added the motion the same day, and TASK-P8-013
carries it to every remaining screen. TASK-P8-014 proved it on every screen on 2026-10-07.

See [docs/01-ROADMAP.md](../01-ROADMAP.md), sub project P8.
