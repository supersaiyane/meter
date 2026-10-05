import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ApiError } from '../../api/client';
import { ExportContext, type ExportView, type RegisterExport } from '../../api/exportViews';
import { costSummaryFixture } from '../../api/fixtures/cost';
import type { ApiShowbackRow } from '../../api/types';
import { violationsIn } from '../../components/__tests__/axe';
import { CostExportScreen } from '../CostExportScreen';
import { Harness } from './Harness';
import { clientReturning, metaOf } from './fixtures';

/** Showback, FEAT-045, delivered through the Export menu, FEAT-067 and TASK-P8-009. */

const SHOWBACK = '/api/v1/cost/showback';

function row(overrides: Partial<ApiShowbackRow> = {}): ApiShowbackRow {
  return {
    billing_period: '2026-08-01',
    account_id: 'fake-platform-a',
    service_name: 'AmazonEC2',
    tag_value: 'platform',
    effective_cost: '900.0000',
    billed_cost: '900.0000',
    line_items: 30,
    as_of: '2026-08-01T00:00:00Z',
    collected_at: '2026-08-24T06:00:00Z',
    accounts_in_file: 5,
    accounts_in_organization: 5,
    ...overrides,
  };
}

const ROWS = [
  row(),
  row({
    account_id: 'fake-product-b',
    service_name: 'AmazonS3',
    tag_value: 'unallocated',
    effective_cost: '100.0000',
    billed_cost: '100.0000',
    line_items: 10,
  }),
];

function renderExport(failure?: Error, register?: RegisterExport) {
  const client = clientReturning(
    {
      '/api/v1/cost/summary': costSummaryFixture(),
      [SHOWBACK]: { data: ROWS, meta: metaOf() },
    },
    failure,
  );
  return render(
    <Harness client={client}>
      <ExportContext.Provider value={register}>
        <CostExportScreen />
      </ExportContext.Provider>
    </Harness>,
  );
}

describe('CostExportScreen', () => {
  it('states the total the file has to add up to', async () => {
    // The screen's one real job beyond the rows. A reader who sums the Effective Cost column
    // in their spreadsheet and gets this figure has checked our arithmetic.
    renderExport();
    const claim = await screen.findByTestId('export-claim');
    expect(claim.textContent).toMatch(/adds up to/);
    expect(claim.querySelector('[data-testid="figure"]')).not.toBeNull();
  });

  it('shows the rows the file holds, the unallocated row named', async () => {
    renderExport();
    const table = await screen.findByRole('table');
    expect(within(table).getByText('fake-platform-a')).toBeInTheDocument();
    expect(within(table).getByTestId('export-unallocated-row')).toHaveTextContent(
      'Unallocated cost',
    );
  });

  it('offers its rows in the Export menu, through the hook that reads them', async () => {
    const offered: ExportView[] = [];
    renderExport(undefined, (view) => {
      offered.push(view);
      return () => undefined;
    });
    await screen.findByRole('table');
    expect(offered).toContainEqual({ title: 'Showback', path: SHOWBACK });
  });

  it('says where the file comes from now that the screen fetches none', async () => {
    renderExport();
    expect(await screen.findByTestId('export-how')).toHaveTextContent(
      /Excel workbook whose About sheet/,
    );
  });

  it('names both measures rather than calling either one cost', async () => {
    renderExport();
    expect(await screen.findByTestId('export-measures')).toHaveTextContent(
      /amortized and billed differ/i,
    );
  });

  it('says the unallocated bucket is a row and is never dropped', async () => {
    renderExport();
    expect(await screen.findByTestId('export-unallocated')).toHaveTextContent(/never dropped/i);
  });

  it('says what failed rather than showing an empty table', async () => {
    renderExport(new ApiError(404, 'No billing period has been collected.'));
    expect(await screen.findByText(/No billing period has been collected/)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('has no accessibility violations', async () => {
    const { container } = renderExport();
    await screen.findByRole('table');
    expect(await violationsIn(container)).toEqual([]);
  });
});
