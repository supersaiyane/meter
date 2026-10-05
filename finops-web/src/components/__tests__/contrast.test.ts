import { describe, expect, it } from 'vitest';

import tokens from '../../tokens.css?raw';

/**
 * Contrast, computed from the tokens rather than trusted.
 *
 * axe cannot do this: `colour-contrast` needs layout and paint, and jsdom has
 * neither, so it reports the rule incomplete and every axe assertion in this
 * suite passes without ever having looked at a colour. This reads the declared
 * values and does the arithmetic.
 *
 * `docs/12-UI-DESIGN.md` section 9 asks for WCAG 2.2 AA generally and AAA on
 * numerals, because misreading a digit is the failure mode that matters in a
 * product whose whole claim is that its numbers can be trusted.
 *
 * Glass, P8 spec section 5.1, is the second reason to compute rather than look.
 * A panel is translucent, so the ground behind its text is the panel composited
 * over the page, and the page is not one colour: it carries three radial glows.
 * Every tier is therefore composited over the bare page and over each glow at
 * its peak, and the smallest ratio is the one held. The glows sit in separate
 * corners, so no two peaks meet.
 */

type Rgba = readonly [r: number, g: number, b: number, a: number];
type Pair = readonly [light: string, dark: string];
type Theme = 'light' | 'dark';

const THEMES: readonly Theme[] = ['light', 'dark'];
const GLOWS = ['--glow-1', '--glow-2', '--glow-3'] as const;
const INKS = ['--text', '--text-muted', '--text-faint'] as const;

/** The two arguments of the first `name: light-dark(a, b)`, nested parentheses kept whole. */
function declared(name: string): Pair {
  const found = new RegExp(`(?:^|\\s)${name}:\\s*light-dark\\(`, 'm').exec(tokens);
  if (found === null) {
    throw new Error(`${name} is not declared as a light-dark pair`);
  }
  const open = found.index + found[0].length - 1;
  let depth = 0;
  let comma = -1;
  for (let at = open; at < tokens.length; at += 1) {
    const character = tokens[at];
    if (character === '(') {
      depth += 1;
    } else if (character === ',' && depth === 1 && comma < 0) {
      comma = at;
    } else if (character === ')') {
      depth -= 1;
      if (depth === 0) {
        if (comma < 0) {
          break;
        }
        return [tokens.slice(open + 1, comma).trim(), tokens.slice(comma + 1, at).trim()];
      }
    }
  }
  throw new Error(`${name} has an unbalanced light-dark pair`);
}

function parse(colour: string): Rgba {
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(colour);
  if (hex?.[1] !== undefined) {
    const digits = hex[1];
    const full =
      digits.length === 3
        ? digits
            .split('')
            .map((d) => d + d)
            .join('')
        : digits;
    return [
      Number.parseInt(full.slice(0, 2), 16),
      Number.parseInt(full.slice(2, 4), 16),
      Number.parseInt(full.slice(4, 6), 16),
      1,
    ];
  }
  const rgb = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)$/i.exec(
    colour,
  );
  if (rgb !== null) {
    return [
      Number(rgb[1]),
      Number(rgb[2]),
      Number(rgb[3]),
      rgb[4] === undefined ? 1 : Number(rgb[4]),
    ];
  }
  throw new Error(`${colour} is not a colour this test can read`);
}

function token(name: string, theme: Theme): Rgba {
  const [light, dark] = declared(name);
  return parse(theme === 'light' ? light : dark);
}

/** `top` painted over an opaque `ground`, the way a browser composites, in sRGB. */
function over(top: Rgba, ground: Rgba): Rgba {
  const [r, g, b, a] = top;
  return [
    r * a + ground[0] * (1 - a),
    g * a + ground[1] * (1 - a),
    b * a + ground[2] * (1 - a),
    1,
  ];
}

function channel(component: number): number {
  const c = component / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance([r, g, b]: Rgba): number {
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function ratio(ink: Rgba, ground: Rgba): number {
  const first = luminance(over(ink, ground));
  const second = luminance(ground);
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
}

/** The page, bare and under each glow's peak. */
function page(theme: Theme): readonly Rgba[] {
  const bare = token('--surface', theme);
  return [bare, ...GLOWS.map((glow) => over(token(glow, theme), bare))];
}

/** A panel at its most transparent, over every point of the page. */
function panels(theme: Theme): readonly Rgba[] {
  return page(theme).map((ground) => over(token('--surface-raised', theme), ground));
}

/** A row raised inside a panel. */
function rows(theme: Theme): readonly Rgba[] {
  return panels(theme).map((ground) => over(token('--surface-raised-2', theme), ground));
}

/** A well, wherever it is set: into the page or into a panel. */
function wells(theme: Theme): readonly Rgba[] {
  return [...page(theme), ...panels(theme)].map((ground) =>
    over(token('--surface-sunken', theme), ground),
  );
}

function lowest(ink: string, grounds: (theme: Theme) => readonly Rgba[]): number {
  return Math.min(
    ...THEMES.flatMap((theme) =>
      grounds(theme).map((ground) => ratio(token(ink, theme), ground)),
    ),
  );
}

describe('contrast, in light and in dark, on glass', () => {
  it('holds text, muted and faint at 4.5 to 1 on every panel tier', () => {
    for (const tier of [panels, rows, wells]) {
      for (const ink of INKS) {
        expect(lowest(ink, tier), `${ink} on ${tier.name}`).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it('gives numerals AAA, because misreading a digit is the failure that matters', () => {
    for (const tier of [page, panels, rows, wells]) {
      expect(lowest('--text-numeral', tier), `numerals on ${tier.name}`).toBeGreaterThanOrEqual(
        7,
      );
    }
  });

  it('gives body text and muted text AA on the page itself', () => {
    // Muted carries provenance labels and freshness, which are not optional.
    for (const ink of ['--text', '--text-muted']) {
      expect(lowest(ink, page), `${ink} on the page`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('gives a failure AA on every ground it is actually drawn on', () => {
    // It was only ever checked against failure-quiet, which is the one ground
    // the trust strip does not use: the shell failures list sits on the page,
    // and a table cell failure sits on a panel. Both were ungated.
    for (const tier of [page, panels, rows, wells]) {
      expect(lowest('--failure', tier), `failure on ${tier.name}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('keeps a failure separable from the body text beside it', () => {
    // The defect this catches is not legibility, it is hierarchy, which is why
    // every contrast check passed while an earlier dark failure, at 2.00
    // against body text, read as quieter than the sentences around it.
    //
    // A failure that does not out shout ordinary prose is a failure a reader
    // scrolls past, and this product's whole claim is that it says when a
    // number is missing.
    for (const theme of THEMES) {
      expect(ratio(token('--failure', theme), token('--text', theme))).toBeGreaterThanOrEqual(
        2.2,
      );
    }
  });

  it('gives a failure and staleness AA against their own quiet grounds', () => {
    for (const theme of THEMES) {
      const failureGround = over(token('--failure-quiet', theme), token('--surface', theme));
      const staleGround = over(token('--stale-quiet', theme), token('--surface', theme));
      expect(ratio(token('--failure', theme), failureGround)).toBeGreaterThanOrEqual(4.5);
      expect(ratio(token('--stale', theme), staleGround)).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('keeps the accent legible as text, since it is the only interactive colour', () => {
    for (const tier of [page, panels]) {
      expect(lowest('--accent', tier), `accent on ${tier.name}`).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('keeps the accent mark at 3 to 1, the bar for a focus ring or a boundary', () => {
    // WCAG 2.2 1.4.11. The mark is never text, so it does not need 4.5.
    for (const tier of [page, panels]) {
      expect(lowest('--accent-mark', tier), `mark on ${tier.name}`).toBeGreaterThanOrEqual(3);
    }
  });

  it('gives the opaque fallback the colour the glass shows over the bare page', () => {
    // Reduced transparency and a browser without backdrop-filter swap glass for
    // these. A different colour would make the setting change the design.
    for (const theme of THEMES) {
      const panel = over(token('--surface-raised', theme), token('--surface', theme));
      const row = over(
        token('--surface-raised-2', theme),
        token('--surface-raised-solid', theme),
      );
      const pairs: readonly (readonly [Rgba, Rgba])[] = [
        [token('--surface-raised-solid', theme), panel],
        [token('--surface-raised-2-solid', theme), row],
      ];
      for (const [solid, glass] of pairs) {
        for (const index of [0, 1, 2] as const) {
          expect(Math.abs(solid[index] - glass[index])).toBeLessThanOrEqual(1);
        }
      }
    }
  });

  it('keeps the rail’s text AA on both of its surfaces', () => {
    // The rail is dark in both themes and its colours are single values, not
    // pairs. Its faint text sat below 4.5 to 1 until axe first ran in a real
    // browser on 2026-10-05, in TASK-P8-002, and caught the menu button and the
    // group headings.
    const single = (name: string): Rgba => {
      const found = new RegExp(`(?:^|\\s)${name}:\\s*(#[0-9a-f]{3,6})`, 'mi').exec(tokens)?.[1];
      if (found === undefined) {
        throw new Error(`${name} is not declared as a single colour`);
      }
      return parse(found);
    };
    for (const ground of ['--nav-surface', '--nav-surface-2']) {
      for (const ink of ['--nav-text', '--nav-text-faint', '--nav-text-strong']) {
        expect(
          ratio(single(ink), single(ground)),
          `${ink} on ${ground}`,
        ).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it('keeps every chart series at 3 to 1 on the page and every panel, the bar for a mark', () => {
    // WCAG 2.2 1.4.11. A series is never text, so it does not need 4.5.
    for (const n of [1, 2, 3, 4, 5, 6]) {
      for (const tier of [page, panels]) {
        expect(
          lowest(`--series-${String(n)}`, tier),
          `series ${String(n)} on ${tier.name}`,
        ).toBeGreaterThanOrEqual(3);
      }
    }
  });

  it('keeps the severity ramp ordered by luminance, not merely different', () => {
    // A categorical palette for an ordered quantity makes HIGH and MEDIUM look
    // like different kinds of thing rather than different amounts.
    const light = [1, 2, 3, 4, 5].map((n) =>
      luminance(token(`--severity-${String(n)}`, 'light')),
    );
    expect([...light].sort((a, b) => b - a)).toEqual(light);
  });
});
