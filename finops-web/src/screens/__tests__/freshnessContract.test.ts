import { describe, expect, it } from 'vitest';

// Read through the bundler rather than through node, which is the same rule
// `surface.test.ts` states and for the same reason: the application project keeps no node
// types, because a module that can reach `process` is one that will eventually read an
// environment variable in the browser.
import app from '../../App.tsx?raw';

/**
 * Every routed screen reports its freshness. ISS-030, closed 2026-09-28 and kept closed here.
 *
 * The issue asked for three things: `as_of` on every fact, freshness on every screen, and a
 * screen dedicated to it. The first is held by two database tests and the third exists. The
 * second was held by nothing at all. It was true when checked by hand and one new screen away
 * from being false, and a screen rendering a number with no freshness is the exact defect
 * constraint 10 exists to prevent, because a stale figure looks identical to a current one.
 *
 * Read from `App.tsx` rather than from a list kept here, because a list would be a second place
 * to forget and would pass while a screen it did not name went unchecked. The route table is what
 * decides what a reader can actually reach.
 *
 * Two files in `screens/` are components rather than screens, `QueryGroups` and
 * `RemediationControls`. Neither is routed, so neither is in the table this reads, and their
 * parent screens report freshness for them. ISS-217 records that they sit in a misleading place.
 */

//: Every screen source, keyed by path. Eager so the test is synchronous, raw so nothing here
//: executes a screen: this reads what was written, not what it renders.
const SOURCES = import.meta.glob('../*.tsx', { query: '?raw', import: 'default', eager: true });

function routedScreens(): string[] {
  // `m[1]` is `string | undefined` under noUncheckedIndexedAccess, and a filter rather than a
  // cast, because a cast here would hide the one case that matters: a regex that matched but
  // captured nothing would silently contribute an empty name to the list.
  const named = [...app.matchAll(/element=\{<([A-Za-z]+)\s*\/>\}/g)]
    .map((match) => match[1])
    .filter((name): name is string => name !== undefined);
  return [...new Set(named)];
}

describe('the freshness contract', () => {
  it('finds the route table, so an empty pass cannot look like a passing one', () => {
    // A regex that stopped matching would make the assertion below vacuous, which is how a
    // test that reads source fails silently.
    expect(routedScreens().length).toBeGreaterThan(15);
  });

  it('has every routed screen report its freshness', () => {
    const missing = routedScreens().filter((name) => {
      const source = SOURCES[`../${name}.tsx`];
      // A routed element that is not a screen file is out of scope rather than a failure: the
      // shell renders a few of its own, and this contract is about screens.
      if (typeof source !== 'string') return false;
      // A call, not a mention. `includes('useReportMeta')` passes on a comment naming it and
      // on a renamed identifier that merely starts with it, which is how the first attempt at
      // falsifying this test failed to make it fail.
      return !/useReportMeta\s*\(/.test(source);
    });
    expect(missing).toEqual([]);
  });
});
