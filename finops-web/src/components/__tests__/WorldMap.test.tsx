import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { LARGEST, SMALLEST, UNSIZED } from '../../screens/geographyModel';
import { WorldMap, type MapGeography } from '../WorldMap';
import { violationsIn } from './axe';

/**
 * The world of dots, TASK-P8-017. The cases that carry this file are the bubble scale, the cost
 * that could not be read, and the geography with no position.
 *
 * A bubble sized by radius rather than by area claims sixteen times the cost for four times the
 * money, which is the oldest lie in data drawing and looks entirely correct. A cost that could not
 * be read must not size anything, and must not be drawn as nought. And a geography the position
 * table has never heard of must be counted, because a drawing that silently omits a continent
 * reports a smaller estate than exists.
 */

const FRESH = { asOf: new Date('2026-10-05T06:00:00Z'), collectedAt: new Date('2026-10-05T06:05:00Z') };

function place(key: string, cost: number | null, resources = 10): MapGeography {
  return {
    key,
    name: `${key} place`,
    resources,
    accounts: 1,
    regions: [`${key}-fake-1`],
    cost,
    links: 0,
  };
}

function radiusOf(key: string): number {
  const marker = screen
    .getAllByTestId('world-map-marker')
    .find((one) => one.getAttribute('data-key') === key);
  return Number(marker?.querySelector('[data-testid="world-map-bubble"]')?.getAttribute('r'));
}

function draw(geographies: readonly MapGeography[], unsized: string | null = null) {
  const onSelect = vi.fn();
  const view = render(
    <WorldMap
      geographies={geographies}
      links={[{ between: ['us', 'eu'], links: 3, kinds: ['PEERS_WITH'] }]}
      unsized={unsized}
      freshness={FRESH}
      selected={null}
      onSelect={onSelect}
    />,
  );
  return { ...view, onSelect };
}

describe('WorldMap', () => {
  it('draws the land as dots on a rounded frame, and no outline that could cross the map', () => {
    draw([place('us', 100)]);
    expect(screen.getByTestId('world-map-land').getAttribute('d')).toMatch(/^M[\d.]+ [\d.]+h0/);
    expect(screen.getByTestId('world-map-frame').getAttribute('d')).toMatch(/Z$/);
  });

  it('sizes bubbles by area, so four times the cost is four times the ink', () => {
    draw([place('us', 400), place('eu', 100)]);
    expect(radiusOf('us')).toBeCloseTo(LARGEST, 6);
    // Four times the cost, so half the radius above the floor, and a quarter of the area.
    expect((radiusOf('eu') - SMALLEST) / (radiusOf('us') - SMALLEST)).toBeCloseTo(0.5, 6);
  });

  it('draws a measured nought as the smallest bubble, a real figure', () => {
    draw([place('us', 400), place('eu', 0)]);
    expect(radiusOf('eu')).toBe(SMALLEST);
  });

  it('sizes nothing by a cost it could not read, and says why', () => {
    draw([place('us', 400), place('eu', 100)], 'The cost could not be read.');
    expect(radiusOf('us')).toBe(UNSIZED);
    expect(radiusOf('eu')).toBe(UNSIZED);
    expect(screen.getByTestId('world-map-caption')).toHaveTextContent('The cost could not be read.');
  });

  it('puts the resource count beside each bubble', () => {
    draw([place('us', 400, 41)]);
    expect(screen.getByTestId('world-map-marker-count')).toHaveTextContent('41 resources');
  });

  it('draws a line between two geographies that are linked, and none to one not drawn', () => {
    draw([place('us', 400), place('eu', 100)]);
    expect(screen.getByTestId('world-map-link').getAttribute('data-between')).toBe('us eu');
    draw([place('us', 400)]);
    // Europe is not on this second drawing, so its line has nowhere to go.
    expect(screen.getAllByTestId('world-map-link')).toHaveLength(1);
  });

  it('counts a geography it cannot position, and draws no bubble for it', () => {
    draw([place('eu', 10), place('zz', 3)]);
    expect(screen.getAllByTestId('world-map-marker')).toHaveLength(1);
    expect(screen.getByTestId('world-map-unplaced')).toHaveTextContent(
      '1 geography is not on the drawing',
    );
  });

  it('says nothing about unplaced geographies when every one is drawn', () => {
    draw([place('eu', 10)]);
    expect(screen.queryByTestId('world-map-unplaced')).toBeNull();
  });

  it('shows a bubble’s numbers on hover and on focus, and hides them after', () => {
    draw([place('eu', 1234.5, 12)]);
    const marker = screen.getByTestId('world-map-marker');
    fireEvent.mouseEnter(marker);
    const tip = screen.getByTestId('world-map-tooltip');
    expect(tip).toHaveTextContent('eu place');
    expect(tip).toHaveTextContent('$1,234.50');
    expect(tip).toHaveTextContent('eu-fake-1');
    expect(marker.getAttribute('aria-describedby')).toBe(tip.id);
    fireEvent.mouseLeave(marker);
    expect(screen.queryByTestId('world-map-tooltip')).toBeNull();
    fireEvent.focus(marker);
    expect(screen.getByTestId('world-map-tooltip')).toHaveTextContent('12');
    fireEvent.blur(marker);
    expect(screen.queryByTestId('world-map-tooltip')).toBeNull();
  });

  it('says a cost it could not read in words in the tooltip, never as nought', () => {
    draw([place('eu', null)], 'Not read.');
    fireEvent.focus(screen.getByTestId('world-map-marker'));
    expect(screen.getByTestId('world-map-tooltip')).toHaveTextContent('Not read');
    expect(screen.getByTestId('world-map-marker').getAttribute('aria-label')).toContain(
      'Effective Cost not read',
    );
  });

  it('chooses a geography by pointer, Enter and Space, and ignores other keys', () => {
    const { onSelect } = draw([place('eu', 10)]);
    const marker = screen.getByTestId('world-map-marker');
    fireEvent.click(marker);
    fireEvent.keyDown(marker, { key: 'Enter' });
    fireEvent.keyDown(marker, { key: ' ' });
    fireEvent.keyDown(marker, { key: 'a' });
    expect(onSelect).toHaveBeenCalledTimes(3);
    expect(onSelect).toHaveBeenCalledWith('eu');
  });

  it('marks the chosen geography on the drawing', () => {
    render(
      <WorldMap
        geographies={[place('eu', 10), place('us', 20)]}
        links={[]}
        unsized={null}
        freshness={FRESH}
        selected="eu"
        onSelect={() => undefined}
      />,
    );
    const pressed = screen
      .getAllByTestId('world-map-marker')
      .map((one) => [one.getAttribute('data-key'), one.getAttribute('aria-pressed')]);
    expect(pressed).toEqual([
      ['eu', 'true'],
      ['us', 'false'],
    ]);
  });

  it('has no accessibility violations, the bubbles being buttons a keyboard reaches', async () => {
    const { container } = draw([place('eu', 10), place('us', 20)]);
    expect(await violationsIn(container)).toEqual([]);
  });
});
