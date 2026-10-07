import { describe, expect, it } from 'vitest';

import layout from '../../layout.css?raw';

/**
 * TASK-P6-012. `forecast` exists as a word before anything is allowed to say it.
 *
 * ADR-0015 sets four conditions on showing a forecast, and the third provenance is only the
 * last of them. So the vocabulary lands alone and this file holds the line: no screen may
 * construct a forecast until somebody decides the other three are met, and when that day
 * comes the decision is made by editing this test, which is where it should be visible.
 *
 * The second half is the defect the task found. A provenance selector written for
 * `modelled` alone leaves a forecast matching nothing, and an unstyled bar is drawn solid,
 * which is how a measurement is drawn.
 */

const SCREENS = import.meta.glob<string>('../../screens/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
});

describe('forecast', () => {
  it('is constructed by the forecast screen alone', () => {
    // TASK-P8-008, 2026-10-05. The owner chose how the other three conditions are met: a
    // weekday profile backtested on held out months with its accuracy published beside the
    // figure, an 80 percent band from those misses, and withheld below three tests or above a
    // 15 percent median miss. The route enforces all three, so the one screen that draws its
    // answer is the one producer, and a second one is a decision this line has to be edited for.
    const files = Object.entries(SCREENS);
    expect(files.length).toBeGreaterThan(20);
    const producers = files
      .filter(([, source]) => /kind:\s*['"]forecast['"]/.test(source))
      .map(([path]) => path);
    expect(producers).toEqual(['../../screens/ForecastScreen.tsx']);
  });

  it('is styled wherever modelled is, so it is never drawn as a measurement', () => {
    const modelled = [
      ...layout.matchAll(/\[data-testid='([a-z-]+)'\]\[data-provenance='modelled'\]/g),
    ].map((match) => match[1]);
    expect(modelled.length).toBeGreaterThan(0);
    for (const component of modelled) {
      expect(layout).toContain(
        `[data-testid='${String(component)}'][data-provenance='forecast']`,
      );
    }
  });
});
