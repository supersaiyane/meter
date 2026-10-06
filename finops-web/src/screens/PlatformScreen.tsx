import { useMemo } from 'react';

import { usePlatformCost } from '../api/queries';
import { dailyByModule, grandTotal, rollUp, type ModuleRow } from './platformRollUp';
import { ChartPanel } from '../components/ChartPanel';
import { StackedArea } from '../components/charts';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { RankedBars } from '../components/RankedBars';
import { Sparkline } from '../components/Sparkline';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * Meter's own cost, by module, with a thirty day shape.
 *
 * `unallocated` appears as a module like any other. Hiding it would make this
 * report tidier and wrong, and a self metering report that under counts is
 * worse than none because it is believed.
 */

const COLUMNS: readonly Column<ModuleRow>[] = [
  { key: 'module', header: 'Module', render: (row) => row.module },
  {
    key: 'total',
    header: 'Effective Cost',
    numeric: true,
    render: (row) => (
      <Figure
        value={{ kind: 'measured', amount: row.total }}
        freshness={{ asOf: new Date(row.asOf), collectedAt: new Date(row.collectedAt) }}
      />
    ),
  },
  {
    key: 'trend',
    header: 'Thirty days',
    render: (row) => (
      <Sparkline points={row.days} provenance="measured" label={`${row.module} daily cost`} />
    ),
  },
];

/** Whole dollars, which is what a chart of a month's spend can show. */
function dollars(value: number): string {
  return `$${value.toLocaleString('en-GB', { maximumFractionDigits: 0 })}`;
}

export function PlatformScreen() {
  const query = usePlatformCost();
  useReportMeta('platform-cost', query.data?.meta);
  const rows = useMemo(() => rollUp(query.data?.data ?? []), [query.data]);
  const state = surfaceStateFor(query, query.data?.meta, rows.length, 'none', 'platform_cost');
  const total = useMemo(() => grandTotal(rows), [rows]);
  const days = useMemo(() => dailyByModule(query.data?.data ?? []), [query.data]);

  return (
    <section aria-label="Meter Cost">
      <StateBoundary state={state}>
        {/* Constraint 7 says the platform meters itself and its own cost is on the front
            page. It was on the front page and not on its own screen, so the one place that
            exists to answer what Meter costs to run made a reader add four rows up. */}
        {total === null ? null : (
          <div data-testid="platform-total">
            <h2>What Meter costs to run</h2>
            <p data-testid="platform-total-figure">
              <Figure
                value={{ kind: 'measured', amount: total.total }}
                freshness={{
                  asOf: new Date(total.asOf),
                  collectedAt: new Date(total.collectedAt),
                }}
              />
            </p>
            {/* The stalest of the four, not the newest, because a total is only as fresh as
                the oldest module in it. `grandTotal` takes the minimum for that reason. */}
            <p data-testid="platform-total-note">
              {rows.length} modules, each tagged `finops:module` so the bill can be split by the
              thing that spent it
            </p>
          </div>
        )}

        <div data-testid="chart-row">
          <ChartPanel
            id="platform-by-module"
            title="Which module it is on"
            caption="Effective Cost by the module that spent it, every day collected"
          >
            <RankedBars
              points={rows.map((row) => ({ label: row.module, value: row.total }))}
              provenance="measured"
              format={dollars}
              restLabel="smaller modules"
            />
          </ChartPanel>
          <ChartPanel
            id="platform-by-day"
            title="Each day, by module"
            caption="Effective Cost per day for the last thirty days, stacked by module"
          >
            <StackedArea
              periods={days.periods}
              series={days.series.map((one) => ({ ...one, provenance: 'measured' as const }))}
              label="Meter's own Effective Cost per day by module"
              format={dollars}
            />
          </ChartPanel>
        </div>

        <DataTable
          rows={rows}
          columns={COLUMNS}
          rowKey={(row) => row.module}
          caption="What Meter costs to run"
        />
      </StateBoundary>
    </section>
  );
}
