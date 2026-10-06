import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { graphCoverageFixture, resourceListFixture } from '../../api/fixtures/topology';
import type { ApiEnvelope, ApiResourceList, ApiTopologyNode } from '../../api/types';
import { violationsIn } from '../../components/__tests__/axe';
import { ResourceListScreen } from '../ResourceListScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';

/**
 * FEAT-056, closing ISS-204.
 *
 * The cases that carry this file are the two claims about the estate, not the table. Rendering
 * an account identifier in a cell is not something anybody gets wrong. What can go wrong is a
 * page that reads as the whole estate: a list with no denominator, and a list drawn from slices
 * that refused us with nothing saying so.
 */

const PATH = '/api/v1/inventory/resources?limit=50&offset=0';

/**
 * One of the fixture's rows, as a row rather than as a possibly absent one.
 *
 * Indexing gives `ApiTopologyNode | undefined` under `noUncheckedIndexedAccess`, and a non null
 * assertion is forbidden here. Throwing says what an empty fixture would actually mean: every
 * case built on that row would pass without testing anything.
 */
function row(index: number): ApiTopologyNode {
  const found = resourceListFixture().data.resources[index];
  if (found === undefined) {
    throw new Error(`the resource fixture has no row ${String(index)}`);
  }
  return found;
}

function pageOf(changes: Partial<ApiResourceList>): ApiEnvelope<ApiResourceList> {
  const base = resourceListFixture();
  return { ...base, data: { ...base.data, ...changes, limit: 50 } };
}

function renderScreen(
  answers: Readonly<Record<string, ApiEnvelope<unknown>>> = {
    [PATH]: pageOf({}),
    '/api/v1/inventory/coverage': graphCoverageFixture(),
  },
) {
  return render(
    <Harness client={clientReturning(answers)} initialPath="/inventory/resources">
      <ResourceListScreen />
    </Harness>,
  );
}

describe('ResourceListScreen, the charts', () => {
  it('draws every resource in scope by type and by region, naming the nulls', async () => {
    const filters = resourceListFixture().data.filters;
    renderScreen({
      [PATH]: pageOf({
        filters: {
          ...filters,
          type_counts: [
            { value: 'AWS::EC2::Instance', resources: 20 },
            { value: null, resources: 7 },
          ],
          region_counts: [
            { value: 'eu-west-1', resources: 25 },
            { value: null, resources: 2 },
          ],
        },
      }),
      '/api/v1/inventory/coverage': graphCoverageFixture(),
    });
    const types = await screen.findByRole('region', { name: 'By type' });
    expect(types).toHaveTextContent('AWS::EC2::Instance');
    expect(types).toHaveTextContent('no type');
    expect(screen.getByRole('region', { name: 'By region' })).toHaveTextContent('global');
  });

  it('draws nothing from a payload made before the counts, rather than empty charts', async () => {
    renderScreen();
    await screen.findByTestId('resources-count');
    expect(screen.queryByTestId('chart-row')).toBeNull();
  });
});

describe('ResourceListScreen', () => {
  it('says how many of how many, so a page does not read as the estate', async () => {
    // The first of the two claims. A list without its denominator reads as complete, and a
    // reader who acts on that is acting on a subset of their estate.
    renderScreen();
    const caption = await screen.findByTestId('resources-count');
    expect(caption).toHaveTextContent('1 to 3 of 27 resources in your scope');
  });

  it('says all of them when the page is the whole scope', async () => {
    // The other half. Saying "1 to 3 of 3" invites a reader to look for a second page that
    // does not exist.
    renderScreen({
      [PATH]: pageOf({ total: 3 }),
      '/api/v1/inventory/coverage': graphCoverageFixture(),
    });
    expect(await screen.findByTestId('resources-count')).toHaveTextContent(
      'All 3 resources in your scope',
    );
  });

  it('names the unreadable slices above the table', async () => {
    // The second claim, and the reason the notice is above rather than below. A slice that
    // refused us contributes no rows while looking exactly like a region that is genuinely
    // empty, and a reader who has read the list has already concluded it was everything.
    renderScreen();
    const banner = await screen.findByTestId('estate-coverage');
    expect(banner).toHaveTextContent(/missing from this list rather than absent/);
    expect(banner).toHaveTextContent('fake-region-c is PARTIAL (NotOptedIn)');
    // Unread is not a synonym for partial, and the screen keeps them apart.
    expect(banner).toHaveTextContent('eu-fake-1 is UNREAD (NotYetAttempted)');
    const bannerTop = banner.compareDocumentPosition(await screen.findByTestId('resources'));
    // DOCUMENT_POSITION_FOLLOWING, so the table comes after the notice.
    expect(bannerTop & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('leads every row to the page about that resource', async () => {
    renderScreen();
    const table = await screen.findByTestId('resources');
    expect(within(table).getByRole('link', { name: 'platform' })).toHaveAttribute(
      'href',
      '/inventory/resources/3f8c1a2b-4d5e-4f60-8a71-9b2c3d4e5f60',
    );
  });

  it('renders a global resource as global rather than as an empty cell', async () => {
    // Null region means global and null zone means regional. Neither is unknown, and a blank
    // cell in a location column reads as missing data.
    renderScreen();
    const table = await screen.findByTestId('resources');
    expect(within(table).getByRole('cell', { name: 'global' })).toBeInTheDocument();
    // And a zonal resource shows its zone, which is the more specific of the two.
    expect(within(table).getByRole('cell', { name: 'us-fake-1-a' })).toBeInTheDocument();
  });

  it('offers only the filter values the estate actually holds', async () => {
    // Read from the data by the server. A select offering fourteen kinds where three exist
    // teaches a reader that eleven of the filters are broken.
    renderScreen();
    // The table first. The selects render before the page arrives, deliberately, because they
    // sit outside the state boundary so a reader can still widen a filter on a failed load.
    // Querying the options before then reads the empty fallback.
    await screen.findByTestId('resources');
    const kinds = screen.getByTestId('filter-kind');
    expect(
      within(kinds)
        .getAllByRole('option')
        .map((one) => one.textContent),
    ).toEqual(['Any', 'IAM_ROLE', 'SUBNET', 'VPC']);
  });

  it('asks the server again when a filter changes', async () => {
    // Server side, because an estate of three hundred accounts is not a list the browser
    // filters. The narrowed request is a different URL, so a client with no stub for it would
    // fail rather than quietly serving the unfiltered answer.
    const user = userEvent.setup();
    renderScreen({
      [PATH]: pageOf({}),
      '/api/v1/inventory/resources?limit=50&offset=0&node_kind=SUBNET': pageOf({
        resources: [row(1)],
        total: 1,
      }),
      '/api/v1/inventory/coverage': graphCoverageFixture(),
    });
    await screen.findByTestId('resources');
    await user.selectOptions(screen.getByTestId('filter-kind'), 'SUBNET');
    await waitFor(() => {
      expect(screen.getByTestId('resources-count')).toHaveTextContent('All 1 resources');
    });
  });

  it('returns to the first page when a filter changes', async () => {
    // Staying on page four of a narrower result shows an empty table, which reads as nothing
    // matches when the truth is that the reader is past the end.
    const user = userEvent.setup();
    renderScreen({
      [PATH]: pageOf({}),
      '/api/v1/inventory/resources?limit=50&offset=50': pageOf({ offset: 50 }),
      // One row and a total of one. A stub with three rows and a total of one produces
      // "1 to 3 of 1", which is the caption telling the truth about a lying fixture.
      '/api/v1/inventory/resources?limit=50&offset=0&node_kind=VPC': pageOf({
        resources: [row(0)],
        total: 1,
      }),
      '/api/v1/inventory/coverage': graphCoverageFixture(),
    });
    await screen.findByTestId('resources');
    await user.click(screen.getByTestId('resources-next'));
    await waitFor(() => {
      expect(screen.getByTestId('resources-count')).toHaveTextContent('51 to 53');
    });
    await user.selectOptions(screen.getByTestId('filter-kind'), 'VPC');
    await waitFor(() => {
      expect(screen.getByTestId('resources-count')).toHaveTextContent('All 1');
    });
  });

  it('disables previous on the first page and next on the last', async () => {
    renderScreen({
      [PATH]: pageOf({ total: 3 }),
      '/api/v1/inventory/coverage': graphCoverageFixture(),
    });
    await screen.findByTestId('resources');
    expect(screen.getByTestId('resources-previous')).toBeDisabled();
    expect(screen.getByTestId('resources-next')).toBeDisabled();
  });

  it('names the filter that emptied the list rather than saying none', async () => {
    // The empty case belongs to `StateBoundary`, which every screen shares. What this screen
    // owes it is the label: "nothing matches this filter, filter: none" over a list the reader
    // just narrowed is how somebody concludes their estate is empty.
    const user = userEvent.setup();
    renderScreen({
      [PATH]: pageOf({}),
      '/api/v1/inventory/resources?limit=50&offset=0&node_kind=IAM_ROLE': pageOf({
        resources: [],
        total: 0,
      }),
      '/api/v1/inventory/coverage': graphCoverageFixture(),
    });
    await screen.findByTestId('resources');
    await user.selectOptions(screen.getByTestId('filter-kind'), 'IAM_ROLE');
    await waitFor(() => {
      expect(screen.getByTestId('state')).toHaveAttribute('data-state', 'empty');
    });
    expect(screen.getByTestId('state')).toHaveTextContent('kind IAM_ROLE');
  });

  it('has no accessibility violations', async () => {
    const { container } = renderScreen();
    await screen.findByTestId('resources');
    expect(await violationsIn(container)).toEqual([]);
  });

  it('names the causes without spilling every slice above the table', async () => {
    // Nine slices is nine lines of identifiers above the fold on a screen whose purpose is the
    // table under them, so the honesty machinery became the first thing a reader saw instead of
    // their own data. The count and the typed causes stay visible; the slices are one click
    // behind. The same treatment the shell's failure wall got, so a reader learns one shape.
    renderScreen();
    const causes = await screen.findByTestId('estate-coverage-causes');
    expect(causes.tagName).toBe('SUMMARY');
    // Collapsed, never dropped. The slices are still in the document, which is what makes this
    // different from hiding them, and the disclosure fetches nothing to open.
    const detail = screen.getByTestId('estate-coverage-detail');
    // The attribute rather than the `open` property, because reading the property needs a cast
    // that eslint removes as unnecessary and tsc then requires, and the attribute is what the
    // markup actually says.
    expect(detail.hasAttribute('open')).toBe(false);
    expect(detail.querySelectorAll('li').length).toBeGreaterThan(0);
  });
});

describe('ResourceListScreen, narrowed by the address', () => {
  it('lands narrowed to the geography a map click carried, and shows it', async () => {
    render(
      <Harness
        initialPath="/inventory/resources?geography=eu"
        client={clientReturning({
          '/api/v1/inventory/resources?limit=50&offset=0&geography=eu': pageOf({}),
          '/api/v1/inventory/coverage': graphCoverageFixture(),
        })}
      >
        <ResourceListScreen />
      </Harness>,
    );
    expect(await screen.findByTestId('resources-count')).toBeInTheDocument();
    expect(screen.getByTestId('filter-geography')).toHaveTextContent('eu');
  });
});
