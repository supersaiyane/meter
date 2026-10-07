import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ApiError } from '../../api/client';
import { reconciliationFixture } from '../../api/fixtures/cost';
import type { ApiReconciliation } from '../../api/types';
import { violationsIn } from '../../components/__tests__/axe';
import { ReconciliationScreen } from '../ReconciliationScreen';
import { Harness } from './Harness';
import { clientReturning, metaOf } from './fixtures';

/** Invoice reconciliation, FEAT-076 and TASK-P10-005: every state in words, never a zero. */

const PATH = '/api/v1/cost/reconciliation';

function renderWith(data: ApiReconciliation = reconciliationFixture().data, failure?: Error) {
  return render(
    <Harness
      client={clientReturning({ [PATH]: { data, meta: metaOf() } }, failure)}
      initialPath="/report/reconciliation"
    >
      <ReconciliationScreen />
    </Harness>,
  );
}

describe('ReconciliationScreen', () => {
  it('says what each comparison means, with the difference signed beside a mismatch', async () => {
    renderWith();
    const rows = await screen.findAllByTestId('reconciliation-row');
    expect(rows.map((row) => row.getAttribute('data-state'))).toEqual([
      'Mismatched',
      'Matched',
      'No rows',
    ]);
    const [mismatch, memo] = rows;
    if (mismatch === undefined || memo === undefined) throw new Error('rows expected');
    expect(within(mismatch).getByTestId('reconciliation-state')).toHaveTextContent(
      'Differs from the invoice',
    );
    expect(within(mismatch).getByTestId('reconciliation-difference')).toHaveTextContent(
      /-\$2\.50/,
    );
    expect(memo).toHaveTextContent('a credit memo correcting fake-invoice-2026-08');
    expect(within(memo).getByTestId('reconciliation-state')).toHaveTextContent(
      'Matches the invoice',
    );
  });

  it('shows an invoice no row carries as not compared, never as a zero', async () => {
    renderWith();
    const rows = await screen.findAllByTestId('reconciliation-row');
    const marketplace = rows.find((row) => row.getAttribute('data-state') === 'No rows');
    if (marketplace === undefined) throw new Error('the Marketplace invoice is missing');
    expect(within(marketplace).getByTestId('reconciliation-state')).toHaveTextContent(
      'No cost row carries this invoice',
    );
    expect(within(marketplace).getByTestId('reconciliation-difference')).toHaveTextContent(
      'Not compared',
    );
  });

  it('is labelled measured and states the modelled tolerance', async () => {
    renderWith();
    const provenance = await screen.findByTestId('reconciliation-provenance');
    expect(provenance).toHaveAttribute('data-provenance', 'measured');
    expect(provenance).toHaveTextContent('within 0.01 percent of the invoice or one cent');
    expect(screen.getByTestId('reconciliation-period')).toHaveTextContent(
      'Billing period starting 2026-08-01, closed.',
    );
  });

  it('says a period is open rather than showing an empty table', async () => {
    renderWith({
      ...reconciliationFixture().data,
      period: '2026-10-01',
      period_status: 'Open',
      state: 'Period open',
      invoices: [],
    });
    const words = await screen.findByTestId('reconciliation-period-state');
    expect(words).toHaveAttribute('data-state', 'Period open');
    expect(words).toHaveTextContent('No invoice has been issued for this period yet');
    expect(screen.queryByTestId('reconciliation-row')).toBeNull();
  });

  it('names the cause of a failed read and shows no figure', async () => {
    renderWith({
      ...reconciliationFixture().data,
      state: 'Not readable',
      cause: 'AccessDenied',
      invoices: [],
    });
    const words = await screen.findByTestId('reconciliation-period-state');
    expect(words).toHaveTextContent('could not be read: AccessDenied');
    expect(words).toHaveTextContent('nothing is shown as zero');
  });

  it("gives a narrowed reader the route's reason and no total", async () => {
    const reason = 'Invoice reconciliation needs the whole organization in view.';
    renderWith(undefined, new ApiError(403, reason));
    expect(await screen.findByTestId('reconciliation-instead')).toHaveTextContent(reason);
    expect(screen.queryByTestId('reconciliation-row')).toBeNull();
  });

  it('says a period nobody has read is unread rather than failed', async () => {
    const reason = 'No invoices have been read for this billing period.';
    renderWith(undefined, new ApiError(404, reason));
    expect(await screen.findByTestId('reconciliation-instead')).toHaveTextContent(reason);
  });

  it('has no accessibility violations', async () => {
    const { container } = renderWith();
    await screen.findAllByTestId('reconciliation-row');
    expect(await violationsIn(container)).toEqual([]);
  });
});
