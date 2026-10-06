import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { GeographyScreen } from '../GeographyScreen';
import { exploreQuery, lastDays } from '../exploreSeries';
import { regionsQuery } from '../geographyModel';
import { Harness } from './Harness';
import { clientReturning, exploreOf } from './fixtures';
import { geographyFixture, resourceListFixture } from '../../api/fixtures/topology';
import type { ApiExplore, ApiExploreRow } from '../../api/types';
import { violationsIn } from '../../components/__tests__/axe';

/**
 * FEAT-061 and TASK-P8-017. The cases that carry this file are the leftovers, the cost that
 * sizes the map, and the deliberate absence of a default continent.
 *
 * A map is the easiest screen in a product to make dishonest, because omitting something looks
 * like tidiness. Resources with no region, resources in a region whose name we cannot read, and
 * resources in a region nobody could read are three different facts with three different
 * remedies, and cost that carries no region is a fourth.
 */

const GEOGRAPHY = '/api/v1/inventory/geography';
const EU = '/api/v1/inventory/resources?limit=25&offset=0&geography=eu';
const US = '/api/v1/inventory/resources?limit=25&offset=0&geography=us';
const EXPLORE = '/api/v1/cost/explore';
const MONTH = `${EXPLORE}?${exploreQuery({ group_by: 'region' })}`;
const WINDOW = lastDays(30, new Date());
const RECENT = `${EXPLORE}?${exploreQuery({ group_by: 'region', period: 'custom', ...WINDOW })}`;

function row(first: string, cost: string, previous = '0'): ApiExploreRow {
  return { first, second: null, this_period: cost, previous_period: previous };
}

/** Cost Explorer's view by region, its regions placed the way the server places them. */
function byRegion(rows: readonly ApiExploreRow[]): ApiExplore {
  return exploreOf({
    group_by: { dimension: 'region', tag_key: null },
    rows,
    rows_omitted: 0,
    omitted_this_period: '0',
    region_geographies: {
      'us-east-1': { key: 'us', name: 'United States' },
      'us-fake-1': { key: 'us', name: 'United States' },
      'eu-fake-1': { key: 'eu', name: 'Europe' },
    },
  });
}

const MONTH_VIEW = byRegion([
  row('us-east-1', '300.00', '250.00'),
  row('us-fake-1', '100.00', '50.00'),
  row('eu-fake-1', '100.00', '100.00'),
  row('unallocated', '50.00'),
  row('zz-west-1', '20.00'),
]);

function renderGeography(stubs: Record<string, unknown> = {}) {
  return render(
    <Harness
      client={clientReturning({
        [GEOGRAPHY]: geographyFixture(),
        [EU]: resourceListFixture(),
        [US]: resourceListFixture(),
        ...stubs,
      })}
    >
      <GeographyScreen />
    </Harness>,
  );
}

function withCost() {
  return renderGeography({
    [MONTH]: { data: MONTH_VIEW, meta: geographyFixture().meta },
    [RECENT]: { data: MONTH_VIEW, meta: geographyFixture().meta },
  });
}

function summaryRow(key: string): HTMLElement {
  const found = within(screen.getByTestId('geography-summary'))
    .getAllByRole('row')
    .find((one) => one.getAttribute('data-key') === key);
  if (found === undefined) throw new Error(`No summary row for ${key}`);
  return found;
}

function radiusOf(key: string): number {
  const marker = screen
    .getAllByTestId('world-map-marker')
    .find((one) => one.getAttribute('data-key') === key);
  return Number(marker?.querySelector('[data-testid="world-map-bubble"]')?.getAttribute('r'));
}

describe('GeographyScreen', () => {
  it('draws the continents from region names and names the regions inside them', async () => {
    renderGeography();
    expect(await screen.findByTestId('world-map')).toBeInTheDocument();
    const choices = screen.getAllByTestId('world-map-choice');
    expect(choices.map((one) => one.getAttribute('data-key'))).toEqual(['us', 'eu']);
    expect(screen.getAllByTestId('geography-tile-estate')[0]).toHaveTextContent('us-fake-1');
  });

  it('says a bubble is a continent and not a datacentre', async () => {
    // The limit of reading geography from a name, stated on the screen rather than in a
    // document nobody opens.
    renderGeography();
    expect(await screen.findByTestId('world-map-caption')).toHaveTextContent(
      /continent and not a datacentre/,
    );
  });

  it('sizes each bubble by this month’s Effective Cost, added up by geography', async () => {
    withCost();
    await screen.findByTestId('geography-cost-global');
    expect(summaryRow('us')).toHaveTextContent('$400.00');
    expect(summaryRow('eu')).toHaveTextContent('$100.00');
    expect(radiusOf('us')).toBeGreaterThan(radiusOf('eu'));
    expect(screen.getByTestId('world-map-caption')).toHaveTextContent(/sized by its Effective Cost/);
  });

  it('keeps cost with no region and cost in an unknown region apart, and off the map', async () => {
    withCost();
    expect(await screen.findByTestId('geography-cost-global')).toHaveTextContent('$50.00');
    expect(screen.getByTestId('geography-cost-unplaced')).toHaveTextContent('zz-west-1');
  });

  it('says when the cost could not be read, and sizes nothing by it', async () => {
    renderGeography();
    expect(await screen.findByTestId('world-map-caption')).toHaveTextContent(
      /could not be read, so every bubble is the same size/,
    );
    expect(summaryRow('us')).toHaveTextContent('Not read');
    expect(radiusOf('us')).toBe(radiusOf('eu'));
    expect(screen.queryByTestId('geography-cost-global')).toBeNull();
  });

  it('draws a line between linked continents and lists every link, inside one too', async () => {
    renderGeography();
    const line = await screen.findByTestId('world-map-link');
    expect(line.getAttribute('data-between')).toBe('eu us');
    const links = within(screen.getByTestId('geography-links'));
    expect(links.getByText('eu-fake-1 and us-east-1')).toBeInTheDocument();
    expect(links.getByText('Europe and United States')).toBeInTheDocument();
    expect(links.getByText('Inside United States, so not drawn')).toBeInTheDocument();
    expect(links.getByText('peering')).toBeInTheDocument();
  });

  it('draws each geography’s trend from its own regions over thirty days', async () => {
    const trend = exploreOf({
      points: [
        { bucket: '2026-10-01', series: 'AmazonEC2', cost: '10.00' },
        { bucket: '2026-10-02', series: 'AmazonEC2', cost: '12.00' },
      ],
    });
    renderGeography({
      [MONTH]: { data: MONTH_VIEW, meta: geographyFixture().meta },
      [RECENT]: { data: MONTH_VIEW, meta: geographyFixture().meta },
      [`${EXPLORE}?${regionsQuery(['eu-fake-1'], WINDOW)}`]: {
        data: trend,
        meta: geographyFixture().meta,
      },
    });
    const europe = await screen.findByRole('region', { name: 'Europe' });
    await within(europe).findByRole('img', { name: /Europe, trend/ });
    // The United States' own view was not stubbed, so its tile says so rather than going quiet.
    const states = screen.getByRole('region', { name: 'United States' });
    expect(await within(states).findByTestId('kpi-note')).toHaveTextContent(
      'The thirty day trend could not be read',
    );
  });

  it('keeps global, unplaceable and refused as three separate answers', async () => {
    // Each needs a different remedy: nothing, one more row in the geography table, and a fix to
    // a collection. One combined count would send somebody to fix IAM for not having a region.
    renderGeography();
    expect(await screen.findByTestId('geography-global')).toHaveTextContent(
      /6 resources have no region at all/,
    );
    expect(screen.getByTestId('geography-unplaceable')).toHaveTextContent(
      /2 resources are in 1 region whose name does not say/,
    );
    expect(screen.getByTestId('geography-refused')).toHaveTextContent(
      /every count above is a floor/,
    );
  });

  it('calls a global resource a fact about the service, not a gap', async () => {
    renderGeography();
    expect(await screen.findByTestId('geography-global')).toHaveTextContent(
      /not a gap in the inventory/,
    );
  });

  it('loads nothing until a continent is chosen', async () => {
    // A screen that loads the first continent has decided which continent matters.
    renderGeography();
    expect(await screen.findByTestId('geography-prompt')).toHaveTextContent(
      /Nothing is loaded until you do/,
    );
    expect(screen.queryByTestId('geography-table')).toBeNull();
  });

  it('lists the resources of the continent that was chosen', async () => {
    renderGeography();
    const choices = await screen.findAllByTestId('world-map-choice');
    const europe = choices.find((one) => one.getAttribute('data-key') === 'eu');
    await userEvent.click(europe as HTMLElement);
    expect(await screen.findByTestId('geography-table')).toBeInTheDocument();
    // The heading repeats the count the map claimed, so a disagreement between the two is
    // visible on one screen rather than needing two.
    expect(screen.getByTestId('geography-chosen')).toHaveTextContent('Europe, 12 resources');
    expect(screen.getByTestId('geography-chosen')).toHaveTextContent('eu-fake-1');
  });

  it('chooses a continent from its bubble as well as its tile', async () => {
    renderGeography();
    await screen.findByTestId('world-map');
    const bubble = screen
      .getAllByTestId('world-map-marker')
      .find((one) => one.getAttribute('data-key') === 'eu') as HTMLElement;
    fireEvent.keyDown(bubble, { key: 'Enter' });
    expect(await screen.findByTestId('geography-chosen')).toHaveTextContent('Europe');
  });

  it('closes the list when the same continent is chosen again', async () => {
    renderGeography();
    const choices = await screen.findAllByTestId('world-map-choice');
    const europe = choices.find((one) => one.getAttribute('data-key') === 'eu') as HTMLElement;
    await userEvent.click(europe);
    expect(await screen.findByTestId('geography-table')).toBeInTheDocument();
    await userEvent.click(europe);
    expect(screen.queryByTestId('geography-table')).toBeNull();
    expect(screen.getByTestId('geography-prompt')).toBeInTheDocument();
  });

  it('publishes the denominator on the list, never a bare page', async () => {
    renderGeography();
    const choices = await screen.findAllByTestId('world-map-choice');
    await userEvent.click(choices[0] as HTMLElement);
    const caption = await screen.findByTestId('geography-table-count');
    expect(caption.textContent).toMatch(/All \d+ of them|The first \d+ of \d+/);
  });

  it('sends a reader to the resource list rather than paging here', async () => {
    renderGeography();
    const choices = await screen.findAllByTestId('world-map-choice');
    await userEvent.click(choices[0] as HTMLElement);
    const table = await screen.findByTestId('geography-resources');
    const more = within(table).queryByTestId('geography-more');
    if (more !== null) {
      expect(more.querySelector('a')).toHaveAttribute('href', '/inventory/resources?geography=us');
    }
  });

  it('has no accessibility violations, with the cost read or not', async () => {
    const { container, unmount } = renderGeography();
    await screen.findByTestId('world-map');
    expect(await violationsIn(container)).toEqual([]);
    unmount();
    const read = withCost();
    await screen.findByTestId('geography-cost-global');
    expect(await violationsIn(read.container)).toEqual([]);
  });
});
