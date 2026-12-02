import { useMemo } from 'react';

import { usePlatformCost } from '../api/queries';
import { rollUp, type ModuleRow } from './platformRollUp';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
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
    header: 'Amortized cost',
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

export function PlatformScreen() {
  const query = usePlatformCost();
  useReportMeta('platform-cost', query.data?.meta);
  const rows = useMemo(() => rollUp(query.data?.data ?? []), [query.data]);
  const state = surfaceStateFor(query, query.data?.meta, rows.length, 'none', 'platform_cost');

  return (
    <section aria-label="Platform cost">
      <StateBoundary state={state}>
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
