import { render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { IngestScreen } from '../IngestScreen';
import type { Run } from '../../api/types';
import { clientReturning, metaOf } from './fixtures';
import { Harness } from './Harness';

function run(partial: Partial<Run>): Run {
  return {
    run_id: partial.run_id ?? '1',
    collector: 'account_health',
    scope_key: 'aws:111122223333:eu-west-1',
    status: 'SUCCEEDED',
    started_at: '2026-08-27T09:00:00Z',
    finished_at: '2026-08-27T09:01:00Z',
    items_written: 0,
    error_type: null,
    error_detail: null,
    ...partial,
  };
}

const ZERO = run({ run_id: 'zero', items_written: 0, scope_key: 'aws:1:eu-west-1' });
const REFUSED = run({
  run_id: 'refused',
  status: 'FAILED',
  items_written: 0,
  error_type: 'AccessDenied',
  error_detail: 'not authorized. Check the StackSet deployment.',
  scope_key: 'aws:2:eu-west-1',
});

function renderScreen(rows: Run[]) {
  return render(
    <Harness
      client={clientReturning({ '/api/v1/ingest/runs': { data: rows, meta: metaOf() } })}
    >
      <IngestScreen />
    </Harness>,
  );
}

describe('IngestScreen', () => {
  it('shows each run per collector and per scope', async () => {
    renderScreen([ZERO, REFUSED]);
    await waitFor(() => {
      expect(screen.getByText('aws:1:eu-west-1')).toBeInTheDocument();
    });
    expect(screen.getByText('aws:2:eu-west-1')).toBeInTheDocument();
  });

  it('makes a failed collection visually distinct from a zero result', async () => {
    // ISS-015. If these two looked alike, every refusal in the product would
    // read as free, and nothing on the page would tell them apart.
    const { container } = renderScreen([ZERO, REFUSED]);
    await waitFor(() => {
      expect(screen.getByText('ACCESS DENIED')).toBeInTheDocument();
    });

    const rows = container.querySelectorAll('tbody tr');
    const zeroRow = within(rows[0] as HTMLElement);
    const refusedRow = within(rows[1] as HTMLElement);

    // The genuine zero goes through Figure and renders a numeral.
    expect(zeroRow.getByTestId('figure')).toBeInTheDocument();
    expect(zeroRow.getByText('0')).toBeInTheDocument();

    // The refusal renders no Figure at all, so there is no numeral to mistake
    // for a zero. Not zero, not a dash, not blank.
    expect(refusedRow.queryByTestId('figure')).toBeNull();
    expect((rows[1] as HTMLElement).querySelector('span.meter-numeral')).toBeNull();
    expect(refusedRow.getByText('ACCESS DENIED')).toBeInTheDocument();
    expect(refusedRow.getByText(/Check the StackSet deployment/)).toBeInTheDocument();
  });

  it('shows a partial run as partial rather than as success', async () => {
    // PARTIAL is the normal outcome at three hundred accounts, and it is not
    // an error state. It must also never read as success.
    renderScreen([run({ run_id: 'p', status: 'PARTIAL', items_written: 297 })]);
    await waitFor(() => {
      expect(screen.getByText('Partial')).toBeInTheDocument();
    });
  });

  it('draws a run failed as Misconfigured as that failure, and never its items as a number', async () => {
    // The local list of causes this screen kept had no Misconfigured, so the run fell through
    // to the number, and a failure read as a measured count. Distinct items, so a stray digit
    // from anywhere else on the row cannot pass for them.
    const misconfigured = run({
      run_id: 'misconfigured',
      status: 'FAILED',
      items_written: 4217,
      error_type: 'Misconfigured',
      error_detail: 'The aggregator named in the settings does not exist.',
    });
    const { container } = renderScreen([misconfigured]);
    await waitFor(() => {
      expect(screen.getByText('MISCONFIGURED')).toBeInTheDocument();
    });
    expect(screen.getByText(/aggregator named in the settings/)).toBeInTheDocument();
    expect(screen.queryByTestId('figure')).toBeNull();
    expect(container.textContent).not.toMatch(/4,?217/);
  });

  it('draws a cause it does not know as drift, and never its items as a number', async () => {
    const unknown = run({
      run_id: 'unknown',
      status: 'FAILED',
      items_written: 4217,
      error_type: 'Exploded',
      error_detail: null,
    });
    const { container } = renderScreen([unknown]);
    await waitFor(() => {
      expect(screen.getByText('UNRECOGNISED')).toBeInTheDocument();
    });
    expect(screen.getByText(/Exploded is not a cause this screen knows/)).toBeInTheDocument();
    expect(screen.queryByTestId('figure')).toBeNull();
    expect(container.textContent).not.toMatch(/4,?217/);
  });

  it('never shows a raw exception string', async () => {
    const { container } = renderScreen([REFUSED]);
    await waitFor(() => {
      expect(screen.getByText('ACCESS DENIED')).toBeInTheDocument();
    });
    expect(container.textContent).not.toContain('Traceback');
  });
});
