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
 */

type Pair = readonly [light: string, dark: string];

function declared(name: string): Pair {
  const match = new RegExp(`${name}:\\s*light-dark\\(([^,]+),\\s*([^)]+)\\)`).exec(tokens);
  const light = match?.[1];
  const dark = match?.[2];
  if (light === undefined || dark === undefined) {
    throw new Error(`${name} is not declared as a light-dark pair`);
  }
  return [light.trim(), dark.trim()];
}

function channel(component: number): number {
  const c = component / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const value = hex.replace('#', '');
  const full =
    value.length === 3
      ? value
          .split('')
          .map((d) => d + d)
          .join('')
      : value;
  const weights = [0.2126, 0.7152, 0.0722];
  return [0, 2, 4].reduce(
    (total, offset, index) =>
      total +
      (weights[index] ?? 0) * channel(Number.parseInt(full.slice(offset, offset + 2), 16)),
    0,
  );
}

function ratio(a: string, b: string): number {
  const first = luminance(a);
  const second = luminance(b);
  const high = Math.max(first, second);
  const low = Math.min(first, second);
  return (high + 0.05) / (low + 0.05);
}

/** Both themes, because neither is derived from the other by inverting. */
function bothModes(fg: string, bg: string): readonly number[] {
  const [fgLight, fgDark] = declared(fg);
  const [bgLight, bgDark] = declared(bg);
  return [ratio(fgLight, bgLight), ratio(fgDark, bgDark)];
}

describe('contrast, in light and in dark', () => {
  it('gives numerals AAA, because misreading a digit is the failure that matters', () => {
    for (const value of bothModes('--text-numeral', '--surface')) {
      expect(value).toBeGreaterThanOrEqual(7);
    }
  });

  it('gives body text AA on both surfaces', () => {
    for (const value of [
      ...bothModes('--text', '--surface'),
      ...bothModes('--text', '--surface-sunken'),
      ...bothModes('--text', '--surface-raised'),
    ]) {
      expect(value).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('keeps muted text legible rather than decorative', () => {
    // It carries provenance labels and freshness, which are not optional.
    for (const value of bothModes('--text-muted', '--surface')) {
      expect(value).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('gives a failure AA on every ground it is actually drawn on', () => {
    // It was only ever checked against failure-quiet, which is the one ground
    // the trust strip does not use: the shell failures list sits on --surface,
    // and a table cell failure sits on --surface-raised. Both were ungated.
    for (const value of [
      ...bothModes('--failure', '--surface'),
      ...bothModes('--failure', '--surface-sunken'),
      ...bothModes('--failure', '--surface-raised'),
    ]) {
      expect(value).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('keeps a failure separable from the body text beside it', () => {
    // The defect this catches is not legibility, it is hierarchy, which is why
    // every contrast check passed while the dark failure read as quieter than
    // the sentences around it. The old dark value sat at 2.00 against body
    // text and fails this; light is 2.26 and the current dark is 2.55.
    //
    // A failure that does not out shout ordinary prose is a failure a reader
    // scrolls past, and this product's whole claim is that it says when a
    // number is missing.
    for (const value of bothModes('--failure', '--text')) {
      expect(value).toBeGreaterThanOrEqual(2.2);
    }
  });

  it('gives a failure AA against its own quiet ground', () => {
    for (const value of bothModes('--failure', '--failure-quiet')) {
      expect(value).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('gives staleness AA against its own ground', () => {
    for (const value of bothModes('--stale', '--stale-quiet')) {
      expect(value).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('keeps the accent legible, since it is the only interactive colour', () => {
    for (const value of bothModes('--accent', '--surface')) {
      expect(value).toBeGreaterThanOrEqual(4.5);
    }
  });

  it('keeps the severity ramp ordered by luminance, not merely different', () => {
    // A categorical palette for an ordered quantity makes HIGH and MEDIUM look
    // like different kinds of thing rather than different amounts.
    const light = [1, 2, 3, 4, 5].map((n) => luminance(declared(`--severity-${String(n)}`)[0]));
    expect([...light].sort((a, b) => b - a)).toEqual(light);
  });
});
