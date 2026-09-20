import { describe, expect, it } from 'vitest';

import * as components from '../index';
// Read through the bundler rather than through node, so the application project
// keeps no node types. A component that can reach process is a component that
// will eventually read an environment variable in the browser.
import tokens from '../../tokens.css?raw';
import layout from '../../layout.css?raw';

/**
 * The public surface is asserted, because the guarantee depends on what is
 * absent from it.
 *
 * If a screen can import a function that turns a number into a string, then
 * under time pressure a screen will, and every figure on that screen loses its
 * provenance without anything failing. This is the same technique as the
 * repository scope guard: the wrong thing is impossible rather than
 * discouraged.
 */
describe('the component surface', () => {
  it('exports no way to render a bare number', () => {
    const forbidden = /^format(Amount|Number|Currency|Cost|Money)$/;
    const offenders = Object.keys(components).filter((name) => forbidden.test(name));
    expect(offenders).toEqual([]);
  });

  it('exports Figure, which is the only path a number takes to a user', () => {
    expect(components.Figure).toBeTypeOf('function');
  });

  it('exports the seven surface states as a list something can check against', () => {
    expect(components.SURFACE_STATES).toHaveLength(7);
  });

  it('keeps the cause vocabulary closed and matching the backend', () => {
    // The six in finops_core.errors, minus NoData which renders as a number and
    // therefore has no label.
    expect(Object.keys(components.CAUSE_LABEL).sort()).toEqual([
      'AccessDenied',
      'NotOptedIn',
      'SchemaDrift',
      'Throttled',
      'Unreachable',
    ]);
    expect(components.rendersAsNumeral('NoData')).toBe(true);
    expect(components.rendersAsNumeral('AccessDenied')).toBe(false);
  });
});

describe('the token layer', () => {
  it('respects reduced motion', () => {
    // Nothing here animates a value anyway, because a number counting up from
    // zero is lying for four hundred milliseconds. This asserts the escape
    // hatch exists for whatever motion is added later.
    expect(tokens).toContain('prefers-reduced-motion: reduce');
  });

  it('defines light and dark in one declaration rather than two blocks', () => {
    // Two blocks drift, and the half that drifts is the one nobody is looking
    // at. light-dark() names both values on the same line.
    expect(tokens).toContain('color-scheme: light dark');
    expect(tokens.match(/light-dark\(/g)?.length ?? 0).toBeGreaterThan(10);
  });

  it('makes numerals tabular so a column aligns by digit', () => {
    expect(tokens).toContain('font-variant-numeric: tabular-nums');
  });

  it('reserves red for failure alone', () => {
    // A large cost is not a failure. Red means one thing so that when it appears
    // it is unambiguous.
    expect(tokens).toContain('--failure:');
    expect(tokens).not.toContain('--cost-high');
  });
});

describe('the visual layer', () => {
  it('introduces no class a component would have to add', () => {
    // The property ADR-0021 was decided on. If this file styled `.card`, some
    // component would have to grow a className to receive it, and the visual
    // layer would become a caller's concern. Every class it targets must
    // already be one the component layer emits.
    const emitted = new Set([
      'meter-numeral',
      'meter-arrives',
      'meter-failure',
      'meter-stale',
      // DataTable emits this for a column declared `prose`, so the explanation
      // takes the width the numeric columns do not need.
      'meter-prose',
      // Figure emits this inside a dense table, so the provenance word sits
      // under its numeral rather than beside it.
      'meter-provenance',
      // OrgTree emits this for the node kind beside a node name.
      'meter-kind',
    ]);
    const withoutComments = layout.replace(/\/\*[\s\S]*?\*\//g, '');
    const targeted = new Set(
      [...withoutComments.matchAll(/\.([a-zA-Z][\w-]*)/g)].map((m) => m[1] as string),
    );
    expect([...targeted].filter((name) => !emitted.has(name))).toEqual([]);
  });

  it('uses borders and never shadows', () => {
    // A shadow implies elevation and physicality, which suits a consumer
    // application and not an instrument.
    expect(layout).toContain('border:');
    expect(layout).not.toMatch(/box-shadow\s*:/);
  });

  it('animates nothing but opacity and background', () => {
    // A number counting up from zero is lying for four hundred milliseconds.
    const transitions = layout.match(/transition:[^;]+;/g) ?? [];
    expect(transitions.length).toBeGreaterThan(0);
    for (const rule of transitions) {
      expect(rule).not.toMatch(/\b(width|height|transform|top|left|all)\b/);
    }
    expect(layout).not.toMatch(/@keyframes/);
  });

  it('applies the severity ramp, so rank is visible and not only labelled', () => {
    for (const level of [1, 2, 3, 4, 5]) {
      expect(layout).toContain(`--severity-${String(level)}`);
    }
  });

  it('carries the three breakpoints section 10 names', () => {
    expect(layout).toContain('max-width: 1280px');
    expect(layout).toContain('max-width: 1024px');
  });

  it('consumes every colour and spacing token that tokens.css declares', () => {
    // The failure ISS-138 recorded was 21 declared tokens nobody used. This
    // fails if a token is added and never consumed, or consumed and then
    // orphaned by a rewrite.
    const declared = [...tokens.matchAll(/^\s*(--[a-z0-9-]+):/gm)].map((m) => m[1]);
    const consumed = new Set([
      ...[...layout.matchAll(/var\((--[a-z0-9-]+)\)/g)].map((m) => m[1]),
      ...[...tokens.matchAll(/var\((--[a-z0-9-]+)\)/g)].map((m) => m[1]),
    ]);
    const orphans = declared.filter(
      (name) =>
        !consumed.has(name as string) &&
        // The type scale is declared whole per section 7. Step 6 is the
        // headline spend figure and has no user until P1 lands one.
        name !== '--font-size-6',
    );
    expect(orphans).toEqual([]);
  });
});
