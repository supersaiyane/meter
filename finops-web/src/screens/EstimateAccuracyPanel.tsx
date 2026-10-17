import { useId, useMemo } from 'react';

import { useEstimateAccuracy } from '../api/queries';
import type { ApiEstimateAccuracyRow } from '../api/types';
import { DataTable } from '../components/DataTable';
import { FreshnessIndicator } from '../components/FreshnessIndicator';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { freshnessOf } from './commitmentFormat';
import { WITHIN_PERCENT, accuracySentence, percentText } from './estimatesModel';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * How close the estimates came, FEAT-097, TASK-P16-008. A modelled estimate set against a
 * measured bill, by resource type and in all, from the judged alone: a resource still waiting for
 * its thirty days, or one that cannot be compared, says nothing about how close an estimate is,
 * so each is counted apart rather than folded in.
 */

const COLUMNS: readonly Column<ApiEstimateAccuracyRow>[] = [
  {
    key: 'type',
    header: 'Resource type',
    rowHeader: true,
    render: (row) => (row.resource_type === 'all' ? 'Every type' : row.resource_type),
  },
  { key: 'compared', header: 'Compared', numeric: true, render: (row) => row.compared },
  {
    key: 'within',
    header: `Within ${WITHIN_PERCENT} percent`,
    numeric: true,
    render: (row) => row.within,
  },
  {
    key: 'error',
    header: 'Median error',
    numeric: true,
    render: (row) =>
      row.median_error_percent === null
        ? 'None compared'
        : percentText(row.median_error_percent),
  },
  { key: 'basis', header: 'Basis', render: (row) => row.basis },
];

export function EstimateAccuracyPanel() {
  const heading = useId();
  const query = useEstimateAccuracy(true);
  const envelope = query.data;
  const found = envelope?.data;
  const types = useMemo(() => found?.types ?? [], [found]);
  useReportMeta('estimate-accuracy', envelope?.meta);
  const state = surfaceStateFor(
    query,
    envelope?.meta,
    types.length,
    'none',
    'estimate_comparison',
  );
  const freshness = freshnessOf(envelope?.meta);
  return (
    <section className="meter-panel" aria-labelledby={heading} data-testid="estimate-accuracy">
      <h2 id={heading}>Against the bill</h2>
      <p data-testid="estimate-accuracy-headline">
        {found === undefined ? null : accuracySentence(found)}
        {envelope?.meta.as_of ? <FreshnessIndicator freshness={freshness} /> : null}
      </p>
      {found === undefined ? null : (
        <p data-testid="estimate-accuracy-waiting">
          {String(found.pending)} waiting for their {String(found.window_days)} billed days, and{' '}
          {String(found.not_compared)} that cannot be compared, each with its reason on its
          plan. Only resources a merged plan created are compared
        </p>
      )}
      <StateBoundary state={state}>
        <DataTable
          rows={types}
          columns={COLUMNS}
          rowKey={(row) => row.resource_type}
          caption="Estimates set against the bill, by resource type"
        />
      </StateBoundary>
    </section>
  );
}
