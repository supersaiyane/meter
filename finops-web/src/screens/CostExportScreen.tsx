import { useState } from 'react';

import { useApi } from '../api/apiContext';
import { useCostSummary } from '../api/queries';
import { Figure } from '../components/Figure';
import { StateBoundary } from '../components/StateBoundary';
import { useReportMeta } from '../shell/metaRegistry';
import { saveFile } from './saveFile';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * The file finance opens. FEAT-045.
 *
 * This screen shows no data of its own, and that is the design rather than a gap. It
 * has one job beyond handing over a file: to state, before the download, the total the
 * file must add up to. A reader who sees that figure here and sums the same column in
 * their spreadsheet has checked our arithmetic, and the figure shown is the one
 * `/cost/summary` gives, which is the one the spend screen shows.
 *
 * So the screen is a claim and a button. The claim is checkable in about ten seconds,
 * which is worth more than any amount of reassurance about the export being correct.
 */

const EXPORT_PATH = '/api/v1/cost/export';

/** What the reader is about to get, named so nobody has to open the file to find out. */
const COLUMNS = [
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
];

type Progress = 'idle' | 'working' | 'saved' | 'failed';

function money(amount: string): number {
  return Number(amount);
}

export function CostExportScreen() {
  const client = useApi();
  const query = useCostSummary();
  const envelope = query.data?.data;
  const summary = envelope?.data;
  const [progress, setProgress] = useState<Progress>('idle');
  const [failure, setFailure] = useState('');

  useReportMeta('cost-export', envelope?.meta);
  const state = surfaceStateFor(
    query,
    envelope?.meta,
    summary ? 1 : 0,
    'none',
    'cost_focus_daily',
  );

  const period = summary?.current.period ?? '';
  const freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };

  async function download() {
    setProgress('working');
    setFailure('');
    try {
      const body = await client.getText(EXPORT_PATH);
      // Named for the period, so two downloads do not overwrite each other in a
      // downloads folder, which is where every one of these files ends up.
      const saved = saveFile(`meter-cost-${period}.csv`, body);
      setProgress(saved ? 'saved' : 'failed');
      if (!saved) {
        setFailure('This browser cannot save a generated file. Call the API directly instead');
      }
    } catch (error) {
      // Said, not swallowed. A download button that silently does nothing is one a
      // reader presses four times and then distrusts the whole screen.
      setProgress('failed');
      setFailure(error instanceof Error ? error.message : 'The export could not be generated');
    }
  }

  return (
    <section aria-label="Export">
      <StateBoundary state={state}>
        <div>
          <p data-testid="export-claim">
            One row per account, service and tag value for {period}. The amortized column adds
            up to{' '}
            <Figure
              value={{
                kind: 'measured',
                amount: money(summary?.current.effective_cost ?? '0'),
              }}
              freshness={freshness}
            />
            , which is the figure on the spend screen. If your spreadsheet disagrees, the export
            is wrong and we want to know
          </p>

          <p data-testid="export-measures">
            Both measures are in the file and both name themselves in the header. Amortized and
            billed differ by exactly the commitment discount, and a column headed only cost is a
            column somebody argues about
          </p>

          <p data-testid="export-unallocated">
            Charges nobody tagged appear as a row named unallocated. They are never dropped and
            never folded into another row, because a file that loses what it cannot attribute
            reports a smaller estate than exists
          </p>

          <ul data-testid="export-columns">
            {COLUMNS.map((column) => (
              <li key={column}>{column}</li>
            ))}
          </ul>

          <button type="button" data-testid="export-download" onClick={() => void download()}>
            {progress === 'working' ? 'Generating' : 'Download CSV'}
          </button>

          {progress === 'saved' ? (
            <p data-testid="export-saved">Saved as meter-cost-{period}.csv</p>
          ) : null}
          {progress === 'failed' ? (
            <p data-testid="export-failed" role="alert">
              {failure}
            </p>
          ) : null}

          <p data-testid="export-not-excel">
            CSV only. An Excel workbook would carry formatting and a sheet name that look like
            decisions somebody made about these figures, and nobody has made them. A spreadsheet
            opens this file directly
          </p>
        </div>
      </StateBoundary>
    </section>
  );
}
