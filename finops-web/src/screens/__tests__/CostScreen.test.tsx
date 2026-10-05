import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { ApiError, type ApiClient } from '../../api/client';
import type { ApiEnvelope, ApiExplore } from '../../api/types';
import { violationsIn } from '../../components/__tests__/axe';
import { CostScreen } from '../CostScreen';
import { Harness } from './Harness';
import { exploreOf, metaOf } from './fixtures';

/**
 * Cost Explorer, FEAT-065 and TASK-P8-007. The view lives in the address, so what a test can
 * see of a control is the query the screen sends, and every query is recorded.
 */
function explorer(answer: () => ApiExplore = () => exploreOf(), failure?: Error) {
  const asked: string[] = [];
  const client: ApiClient = {
    get: <T,>(path: string): Promise<ApiEnvelope<T>> => {
      const [route = '', query = ''] = path.split('?');
      if (route !== '/api/v1/cost/explore')
        return Promise.reject(new Error(`no stub: ${path}`));
      asked.push(query);
      if (failure) return Promise.reject(failure);
      return Promise.resolve({ data: answer(), meta: metaOf() } as unknown as ApiEnvelope<T>);
    },
    getFile: () => Promise.reject(new Error('no file stub')),
    post: () => Promise.reject(new Error('no write stub')),
  };
  return { client, asked };
}

function renderExplorer(stub = explorer(), initialPath = '/analyze/explorer') {
  const view = render(
    <Harness client={stub.client} initialPath={initialPath}>
      <CostScreen />
    </Harness>,
  );
  return { ...view, asked: stub.asked };
}

describe('CostScreen, Cost Explorer: what it shows', () => {
  it('asks for the default view and says which period it is and that it is still open', async () => {
    const { asked } = renderExplorer();
    expect(await screen.findByTestId('cost-period')).toHaveTextContent(
      '1 to 5 October 2026, month to date, compared with 1 to 5 September 2026',
    );
    expect(screen.getByText(/still open/)).toBeInTheDocument();
    expect(asked).toEqual(['']);
  });

  it('shows this period, the period before and the change as three tiles', async () => {
    renderExplorer();
    const tiles = await screen.findAllByTestId('kpi-tile');
    expect(tiles.map((tile) => within(tile).getByTestId('kpi-value').textContent)).toEqual([
      '$4,512.71',
      '$4,203.10',
      '+$309.61',
    ]);
  });

  it('draws the chart by the first grouping, with unallocated named and the rest as one', async () => {
    renderExplorer();
    const chart = await screen.findByTestId('explore-chart');
    expect(within(chart).getAllByText('Unallocated').length).toBeGreaterThan(0);
    expect(within(chart).getAllByText('Everything else').length).toBeGreaterThan(0);
  });

  it('totals the table to the whole period, with a row for what the limit left out', async () => {
    const answer = exploreOf();
    renderExplorer(
      explorer(() => ({
        ...answer,
        rows: answer.rows.slice(0, 2),
        rows_omitted: 2,
        omitted_this_period: '1100.00',
        omitted_previous_period: '1090.00',
      })),
    );
    expect(await screen.findByText('2 more rows')).toBeInTheDocument();
    expect(screen.getByTestId('total-this')).toHaveTextContent('4,512.71');
    expect(screen.getByTestId('total-previous')).toHaveTextContent('4,203.10');
  });

  it('says the period before was not collected rather than showing it as nothing', async () => {
    const answer = exploreOf();
    renderExplorer(
      explorer(() => ({
        ...answer,
        previous_collected: false,
        total_previous_period: null,
        omitted_previous_period: null,
        rows: answer.rows.map((row) => ({ ...row, previous_period: null })),
      })),
    );
    expect(await screen.findAllByText('Not collected')).toHaveLength(4);
    expect(screen.getByTestId('total-previous')).toHaveTextContent(
      'No total: a figure was not collected',
    );
  });

  it('groups two ways in one table, and sorts it by any column', async () => {
    const user = userEvent.setup();
    const answer = exploreOf();
    const regions = ['eu-west-2', 'us-east-1', 'unallocated', 'eu-west-2'];
    renderExplorer(
      explorer(() => ({
        ...answer,
        then_by: { dimension: 'region', tag_key: null },
        rows: answer.rows.map((row, index) => ({ ...row, second: regions[index] ?? null })),
      })),
    );
    const table = within(await screen.findByTestId('explore-table'));
    expect(table.getAllByRole('link', { name: 'eu-west-2' })).toHaveLength(2);
    // One in each grouping: an unallocated service row and an unallocated region.
    expect(table.getAllByRole('link', { name: 'Unallocated' })).toHaveLength(2);
    for (const header of ['Service', 'Region', 'This period', 'Previous period', 'Change']) {
      const column = table.getByRole('columnheader', { name: new RegExp(`^${header}`) });
      await user.click(within(column).getByRole('button'));
      expect(column).toHaveAttribute('aria-sort');
      expect(column.getAttribute('aria-sort')).not.toBe('none');
    }
  });

  it('keeps its controls when the route refuses a view, so the view can be changed', async () => {
    renderExplorer(explorer(undefined, new ApiError(422, 'Group by two different things.')));
    expect(await screen.findByText(/Group by two different things/)).toBeInTheDocument();
    expect(screen.getByLabelText('Group by')).toBeInTheDocument();
  });

  it('passes an accessibility check', async () => {
    const { container } = renderExplorer();
    await screen.findByTestId('cost-period');
    expect(await violationsIn(container)).toEqual([]);
  });
});

describe('CostScreen, Cost Explorer: what a reader changes', () => {
  it('filters to a value by its link, and takes the filter away by its chip', async () => {
    const user = userEvent.setup();
    const { asked } = renderExplorer();
    await user.click(await screen.findByRole('link', { name: 'AmazonEC2' }));
    expect(asked.at(-1)).toBe('service=AmazonEC2');
    await user.click(
      await screen.findByRole('button', { name: 'Remove the filter Service: AmazonEC2' }),
    );
    expect(asked.at(-1)).toBe('');
    expect(screen.getByText(/No filters/)).toBeInTheDocument();
  });

  it('groups a second way when asked', async () => {
    const user = userEvent.setup();
    const { asked } = renderExplorer();
    await screen.findByTestId('cost-period');
    await user.selectOptions(screen.getByLabelText('Then by'), 'region');
    expect(asked.at(-1)).toBe('then_by=region');
    await user.selectOptions(screen.getByLabelText('Then by'), '');
    expect(asked.at(-1)).toBe('');
  });

  it('groups by a tag key the period offers, a colon in the key kept whole', async () => {
    const user = userEvent.setup();
    const { asked } = renderExplorer();
    await screen.findAllByRole('option', { name: 'Tag: finops:module' });
    await user.selectOptions(screen.getByLabelText('Group by'), 'tag:finops:module');
    expect(asked.at(-1)).toBe('group_by=tag&group_by_tag=finops%3Amodule');
  });

  it('keeps a tag grouping from an older link in the list, so the select says what is asked', async () => {
    renderExplorer(explorer(), '/analyze/explorer?group_by=tag&group_by_tag=retired');
    expect(await screen.findByRole('option', { name: 'Tag: retired' })).toBeInTheDocument();
  });

  it('moves the second grouping aside when the first takes its place', async () => {
    const user = userEvent.setup();
    const { asked } = renderExplorer(explorer(), '/analyze/explorer?then_by=region');
    await screen.findByTestId('cost-period');
    await user.selectOptions(screen.getByLabelText('Group by'), 'region');
    expect(asked.at(-1)).toBe('group_by=region');
  });

  it('reads by month when asked', async () => {
    const user = userEvent.setup();
    const { asked } = renderExplorer();
    await screen.findByTestId('cost-period');
    await user.click(screen.getByLabelText('Monthly'));
    expect(asked.at(-1)).toBe('granularity=monthly');
  });

  it('opens a custom period at the window on screen, and clears its dates for a preset', async () => {
    const user = userEvent.setup();
    const { asked } = renderExplorer();
    await screen.findByTestId('cost-period');
    await user.click(screen.getByLabelText('Custom'));
    expect(asked.at(-1)).toBe('period=custom&start=2026-10-01&end=2026-10-05');
    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-10-02' } });
    expect(asked.at(-1)).toBe('period=custom&start=2026-10-02&end=2026-10-05');
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-10-04' } });
    expect(asked.at(-1)).toBe('period=custom&start=2026-10-02&end=2026-10-04');
    await user.click(screen.getByLabelText('3 months'));
    expect(asked.at(-1)).toBe('period=3m');
  });

  it('offers only the measures every line item carries', async () => {
    const user = userEvent.setup();
    const { asked } = renderExplorer();
    await screen.findByRole('option', { name: 'List Cost' });
    const measure = screen.getByLabelText('Measure');
    expect(
      within(measure)
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual(['Effective Cost', 'Billed Cost', 'List Cost']);
    await user.selectOptions(measure, 'billed_cost');
    expect(asked.at(-1)).toBe('metric=billed_cost');
  });
});
