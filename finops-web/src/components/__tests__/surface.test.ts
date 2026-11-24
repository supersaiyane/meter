import { describe, expect, it } from 'vitest';

import * as components from '../index';
// Read through the bundler rather than through node, so the application project
// keeps no node types. A component that can reach process is a component that
// will eventually read an environment variable in the browser.
import tokens from '../../tokens.css?raw';

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
