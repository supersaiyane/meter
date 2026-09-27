import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { WorldMap } from '../WorldMap';
import type { ApiGeography } from '../../api/types';
import { violationsIn } from './axe';

/**
 * The two cases that carry this file are the marker scale and the geography with no position.
 *
 * A marker sized by radius rather than by area claims four times the estate for twice the
 * resources, which is the oldest lie in data drawing and looks entirely correct. And a geography
 * the position table has never heard of must stay in the legend and be counted, because a drawing
 * that silently omits a continent reports a smaller estate than exists, which is the same failure
 * as rendering a collection error as the number zero.
 */

function place(key: string, resources: number): ApiGeography {
  return { key, name: `${key} place`, regions: [`${key}-fake-1`], resources, accounts: 1 };
}

function radiusOf(marker: Element): number {
  return Number(marker.querySelector('circle')?.getAttribute('r'));
}

describe('WorldMap', () => {
  it('sizes markers by area, so four times the resources is four times the ink', () => {
    render(
      <WorldMap
        geographies={[place('us', 400), place('eu', 100)]}
        selected={null}
        onSelect={() => undefined}
      />,
    );
    const markers = screen.getAllByTestId('world-map-marker');
    const big = radiusOf(markers[0] as Element);
    const small = radiusOf(markers[1] as Element);
    // Four times the resources, so twice the radius and therefore four times the area. The
    // scale runs from a floor, so the relationship is checked on the part above it.
    const floor = 7;
    expect((big - floor) / (small - floor)).toBeCloseTo(2, 1);
  });

  it('keeps a geography it cannot position in the legend and says so', () => {
    // The honesty rule, one level down from the route's. `zz` is not in the position table and
    // never will be, and its resources are still part of the estate.
    render(
      <WorldMap
        geographies={[place('eu', 10), place('zz', 3)]}
        selected={null}
        onSelect={() => undefined}
      />,
    );
    // One marker drawn, two rows in the legend.
    expect(screen.getAllByTestId('world-map-marker')).toHaveLength(1);
    expect(screen.getAllByTestId('world-map-choice')).toHaveLength(2);
    expect(screen.getByTestId('world-map-unplaced')).toHaveTextContent(
      '1 geography is not on the drawing',
    );
  });

  it('says nothing about unplaced geographies when every one is drawn', () => {
    render(
      <WorldMap geographies={[place('eu', 10)]} selected={null} onSelect={() => undefined} />,
    );
    expect(screen.queryByTestId('world-map-unplaced')).toBeNull();
  });

  it('names the regions inside a continent, because the prefix cannot', () => {
    // The limit of the whole approach, admitted in the legend rather than in a footnote. A
    // reader looking at Europe needs to know whether that is Dublin, Frankfurt or both.
    render(
      <WorldMap
        geographies={[
          {
            key: 'eu',
            name: 'Europe',
            regions: ['eu-west-1', 'eu-central-1'],
            resources: 5,
            accounts: 2,
          },
        ]}
        selected={null}
        onSelect={() => undefined}
      />,
    );
    expect(screen.getByTestId('world-map-regions')).toHaveTextContent(
      'eu-west-1, eu-central-1',
    );
  });

  it('marks the chosen continent on the drawing and in the legend', () => {
    render(
      <WorldMap
        geographies={[place('us', 10), place('eu', 5)]}
        selected="eu"
        onSelect={() => undefined}
      />,
    );
    const chosen = screen
      .getAllByTestId('world-map-choice')
      .find((one) => one.getAttribute('data-key') === 'eu');
    expect(chosen).toHaveAttribute('aria-pressed', 'true');
    const marker = screen
      .getAllByTestId('world-map-marker')
      .find((one) => one.getAttribute('data-key') === 'eu');
    expect(marker).toHaveAttribute('data-selected', 'true');
  });

  it('hides the drawing from the accessibility tree and keeps a real control', async () => {
    // The picture is a faster way to compare numbers that are all written out beneath it, and
    // the markers cannot be reached from a keyboard. The buttons can.
    const { container } = render(
      <WorldMap geographies={[place('eu', 10)]} selected={null} onSelect={() => undefined} />,
    );
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
    expect(screen.getByTestId('world-map-choice').tagName).toBe('BUTTON');
    expect(await violationsIn(container)).toEqual([]);
  });
});
