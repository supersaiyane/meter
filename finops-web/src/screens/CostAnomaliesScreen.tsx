import { useMemo } from 'react';

import { useCostAnomalies } from '../api/queries';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { SeverityBadge } from '../components/SeverityBadge';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { severityLevel } from './querySeverity';
import { surfaceStateFor } from './surfaceStateFor';
import type { ApiCostAnomaly } from '../api/types';

/**
 * Days that did not look like the days before them. FEAT-023.
 *
 * The hardest thing on this screen is the empty state, because an empty list
 * means two opposite things. An estate with a fortnight of history and nothing
 * wrong is behaving, and saying so is useful. An estate with four days of
 * history has not been judged at all, and telling that one it has no anomalies
 * is a reassuring lie it will act on.
 *
 * So the payload carries how many days have been collected, and this screen
 * says which of the two situations the reader is in.
 *
 * Every row carries three numbers and its working. A percentage alone is not
 * actionable: somebody has to know the money before they can decide whether to
 * care, and the baseline before they can disagree.
 */

function money(amount: string): number {
  return Number(amount);
}

export function CostAnomaliesScreen() {
  const query = useCostAnomalies();
  const envelope = query.data?.data;
  const found = envelope?.data;
  const rows = useMemo(() => found?.anomalies ?? [], [found]);

  useReportMeta('cost-anomalies', envelope?.meta);
  const state = surfaceStateFor(query, envelope?.meta, rows.length, 'none', 'cost_anomaly');

  const freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };

  const judgeable = (found?.days_collected ?? 0) >= (found?.days_needed ?? 0);

  const columns: readonly Column<ApiCostAnomaly>[] = [
    {
      key: 'severity',
      header: 'Severity',
      // The same mapping the query findings use, so two screens do not mean
      // different things by the word high.
      render: (row) => <SeverityBadge level={severityLevel(row.severity)} />,
    },
    { key: 'day', header: 'Day', render: (row) => row.day },
    {
      key: 'what',
      header: 'Account and service',
      render: (row) => `${row.account_id} ${row.service_name}`,
    },
    {
      key: 'delta',
      header: 'More than usual',
      numeric: true,
      render: (row) => (
        <Figure value={{ kind: 'measured', amount: money(row.delta) }} freshness={freshness} />
      ),
    },
    {
      key: 'observed',
      header: 'That day',
      numeric: true,
      render: (row) => (
        <Figure
          value={{ kind: 'measured', amount: money(row.observed) }}
          freshness={freshness}
        />
      ),
    },
    {
      key: 'baseline',
      header: 'Usually',
      numeric: true,
      render: (row) => (
        <Figure
          value={{ kind: 'measured', amount: money(row.baseline) }}
          freshness={freshness}
        />
      ),
    },
    {
      key: 'why',
      header: 'Why',
      // Whole, never shortened. A verdict a reader cannot argue with is one
      // they have to take on trust, and nobody takes a cost alert on trust
      // twice.
      prose: true,
      render: (row) => row.why,
    },
  ];

  return (
    <section aria-label="Anomalies">
      {/*
        Outside the boundary on purpose. This sentence is about whether the
        estate can be judged at all, which is a fact about the screen rather
        than about the request, and the boundary takes over the moment there
        are no rows. Inside it, the one distinction this screen exists to draw
        would be the one thing a reader never sees.
      */}
      <p data-testid="anomaly-context">
        {judgeable ? (
          <span data-testid="anomaly-judged">
            {found?.days_collected} days collected, which is enough to judge against
          </span>
        ) : (
          // Not "no anomalies". Nothing here has been judged, and a reader
          // who takes silence for safety will act on it.
          <span data-testid="anomaly-too-young">
            Only {found?.days_collected} days collected. Nothing can be judged until there are{' '}
            {found?.days_needed}, so this page is empty because nobody has looked yet, not
            because nothing is wrong
          </span>
        )}
      </p>

      {judgeable && rows.length === 0 ? (
        <p data-testid="anomaly-none">
          No day in the last fortnight stood out from the days before it
        </p>
      ) : null}

      <StateBoundary state={state}>
        <DataTable
          rows={rows}
          columns={columns}
          rowKey={(row) => `${row.account_id}:${row.service_name}:${row.day}`}
          caption={`${String(rows.length)} ${
            rows.length === 1 ? 'day' : 'days'
          } that stood out, biggest first`}
        />
      </StateBoundary>
    </section>
  );
}
