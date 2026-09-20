import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CostExportScreen } from '../CostExportScreen';
import { Harness } from './Harness';
import { clientReturning } from './fixtures';
import { costSummaryFixture } from '../../api/fixtures/cost';
import { violationsIn } from '../../components/__tests__/axe';

const EXPORT_PATH = '/api/v1/cost/export';

/**
 * A file shaped like the real one, so the screen's claim can be read against it
 * rather than taken on trust.
 */
const CSV = [
  [
    'billing_period',
    'account_id',
    'service_name',
    'tag_value',
    'effective_cost_amortized_usd',
    'billed_cost_usd',
    'line_items',
    'as_of',
    'collected_at',
    'accounts_in_file',
    'accounts_in_organization',
  ].join(','),
  '2026-08-01,fake-platform-a,AmazonEC2,platform,900.0000,900.0000,30,2026-08-01T00:00:00Z,2026-08-24T06:00:00Z,5,5',
  '2026-08-01,fake-product-b,AmazonS3,unallocated,100.0000,100.0000,10,2026-08-01T00:00:00Z,2026-08-24T06:00:00Z,5,5',
].join('\n');

function renderExport(files: Readonly<Record<string, string>> = { [EXPORT_PATH]: CSV }) {
  return render(
    <Harness
      client={clientReturning(
        { '/api/v1/cost/summary': costSummaryFixture() },
        undefined,
        files,
      )}
    >
      <CostExportScreen />
    </Harness>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('CostExportScreen', () => {
  it('states the total the file has to add up to', async () => {
    // The screen's one real job beyond handing over a file. A reader who sums the
    // amortized column in their spreadsheet and gets this figure has checked our
    // arithmetic, which is worth more than any reassurance that the export is right.
    renderExport();
    const claim = await screen.findByTestId('export-claim');
    expect(claim.textContent).toMatch(/adds up to/);
    expect(claim.querySelector('[data-testid="figure"]')).not.toBeNull();
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

  it('lists the columns, both timestamps included', async () => {
    // The freshness in the file is why this route may skip the meta envelope, so the
    // screen has to show that it is there.
    renderExport();
    const columns = await screen.findByTestId('export-columns');
    expect(columns.textContent).toContain('effective_cost_amortized_usd');
    expect(columns.textContent).toContain('as_of');
    expect(columns.textContent).toContain('collected_at');
    expect(columns.textContent).toContain('accounts_in_file');
  });

  it('says plainly that Excel is not on offer and why', async () => {
    renderExport();
    expect(await screen.findByTestId('export-not-excel')).toHaveTextContent(/CSV only/);
  });

  it('downloads the file and names it for the period', async () => {
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: vi.fn(() => 'blob:meter'),
      revokeObjectURL: vi.fn(),
    });
    // Spied rather than stashed and restored by hand. Holding a reference to a
    // prototype method loses its `this`, and vitest puts the real one back for us.
    const clicked: string[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function recorded(
      this: HTMLAnchorElement,
    ) {
      clicked.push(this.download);
    });

    renderExport();
    await userEvent.click(await screen.findByTestId('export-download'));
    await waitFor(() => {
      expect(screen.getByTestId('export-saved')).toBeInTheDocument();
    });
    expect(clicked).toEqual(['meter-cost-2026-08-01.csv']);
  });

  it('says so when the export cannot be generated rather than doing nothing', async () => {
    // A download button that silently does nothing is one a reader presses four times
    // and then distrusts the whole screen.
    renderExport({});
    await userEvent.click(await screen.findByTestId('export-download'));
    const failed = await screen.findByTestId('export-failed');
    expect(failed).toHaveAttribute('role', 'alert');
    expect(failed.textContent).toMatch(/no file stub/);
  });

  it('says so when the browser cannot save a generated file', async () => {
    // Rather than throwing. An old browser should leave the reader with a sentence,
    // not a blank page.
    vi.stubGlobal('URL', { ...URL, createObjectURL: undefined });
    renderExport();
    await userEvent.click(await screen.findByTestId('export-download'));
    expect(await screen.findByTestId('export-failed')).toHaveTextContent(/cannot save/i);
  });

  it('has no accessibility violations', async () => {
    const { container } = renderExport();
    await screen.findByTestId('export-download');
    expect(await violationsIn(container)).toEqual([]);
  });
});
