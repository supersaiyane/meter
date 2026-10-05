import { act, render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { App } from '../../App';
import type { ApiClient } from '../../api/client';
import {
  COMMITMENT_TYPE_NAMES,
  COLLECTOR_NAMES,
  LIFECYCLE_NAMES,
} from '../../components/displayNames';
import { TABS, allScreens } from '../../shell/sections';

/**
 * TASK-P8-004: no raw identifier on any screen, collector names and enum codes
 * included, held over the text a person actually reads.
 *
 * Every surface answers with its fixture here, so each screen renders a page of
 * data rather than a loading state, and the text this reads is the text the
 * screen would show.
 */
vi.mock('../../api/fixtureSeam', async (importOriginal) => {
  const original = await importOriginal<typeof import('../../api/fixtureSeam')>();
  return {
    ...original,
    resolveSurface:
      <T,>(_template: string, _live: () => Promise<T>, fixture: () => T) =>
      () =>
        Promise.resolve({ data: fixture(), source: 'route' as const }),
  };
});

const NEVER_ANSWERS: ApiClient = {
  get: () => new Promise(() => undefined),
  getFile: () => new Promise<never>(() => undefined),
  post: () => new Promise(() => undefined),
};

/** Every built screen, and every tab of one. */
const PAGES = [
  ...new Set([
    ...allScreens()
      .filter((screen) => screen.arrives === null)
      .map((screen) => screen.path),
    ...Object.values(TABS)
      .flat()
      .map((tab) => tab.path),
  ]),
];

/**
 * What a raw identifier looks like. A collector name with an underscore, since
 * a one word collector such as budgets is also an ordinary word, and the state
 * codes that are single upper case words.
 *
 * Two shapes are references a person acts on rather than codes to translate,
 * and are left alone: a Meter setting named in an instruction, such as
 * METER_ASSISTANT_MODEL_ID, which an operator has to type exactly, and a
 * register reference such as OPEN-10.
 */
const RAW: readonly RegExp[] = [
  /\b(?!METER_)[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b/,
  new RegExp(
    `\\b(?:${Object.keys(COLLECTOR_NAMES)
      .filter((code) => code.includes('_'))
      .join('|')})\\b`,
  ),
  new RegExp(`\\b(?:${Object.keys(COMMITMENT_TYPE_NAMES).join('|')})\\b`),
  new RegExp(
    `\\b(?:${Object.keys(LIFECYCLE_NAMES).join('|')}|INCONCLUSIVE|HEALTHY)\\b(?!-\\d)`,
  ),
];

describe('no raw identifier on any screen', () => {
  it('shows every code and collector in words, on every built screen and tab', async () => {
    const found: string[] = [];
    for (const path of PAGES) {
      window.history.pushState({}, '', path);
      const { unmount } = render(<App client={NEVER_ANSWERS} />);
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
      });
      const text = document.body.textContent;
      for (const pattern of RAW) {
        const match = pattern.exec(text);
        if (match !== null) {
          found.push(`${path}: ${match[0]}`);
        }
      }
      unmount();
    }
    expect(found).toEqual([]);
  });
});
