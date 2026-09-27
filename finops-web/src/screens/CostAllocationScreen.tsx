import { useMemo, useState } from 'react';

import { useCostAllocation } from '../api/queries';
import { DataTable } from '../components/DataTable';
import { RankedBars } from '../components/RankedBars';
import { Figure } from '../components/Figure';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { surfaceStateFor } from './surfaceStateFor';
import type { ApiCostSlice } from '../api/types';

/**
 * Whose spend it is, as far as the tags can say. FEAT-022.
 *
 * The unallocated row is the point of this screen. Every estate has one and
 * most are embarrassed by it, which is exactly why it is rendered as a row like
 * any other rather than dropped or folded into a total. A view that quietly
 * loses what it cannot attribute reports a smaller estate than exists, and the
 * gap between that number and the invoice is the first thing finance finds.
 *
 * The tag key is chosen here rather than fixed, because which key means
 * ownership is an estate's decision and not ours. There is no default at the
 * API: guessing one would group an estate by something nobody asked for and
 * then label it their allocation.
 */

/** What the API calls a charge nobody tagged. Matched, never re-derived. */
const UNALLOCATED = 'unallocated';

/** Keys an estate is likely to use. A starting point, not a restriction. */
const SUGGESTED = ['team', 'service', 'environment', 'cost-centre'] as const;

function money(amount: string): number {
  return Number(amount);
}

export function CostAllocationScreen() {
  const [tag, setTag] = useState<string>(SUGGESTED[0]);
  const query = useCostAllocation(tag);
  const envelope = query.data?.data;
  const rows = useMemo(() => envelope?.data ?? [], [envelope]);

  useReportMeta('cost-allocation', envelope?.meta);
  const state = surfaceStateFor(query, envelope?.meta, rows.length, 'none', 'cost_focus');

  const freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };

  const total = rows.reduce((sum, row) => sum + money(row.effective_cost), 0);
  const unallocated = rows.find((row) => row.name === UNALLOCATED);
  const share = total > 0 && unallocated ? money(unallocated.effective_cost) / total : 0;

  const columns: readonly Column<ApiCostSlice>[] = [
    {
      key: 'owner',
      header: `By ${tag}`,
      render: (row) =>
        row.name === UNALLOCATED ? (
          // Named, not blank. An empty cell reads as a rendering fault and
          // sends somebody looking for a value that was never there.
          <span data-testid="allocation-unallocated">nobody tagged this</span>
        ) : (
          row.name
        ),
    },
    {
      key: 'cost',
      header: 'Amortized',
      numeric: true,
      render: (row) => (
        <Figure
          value={{ kind: 'measured', amount: money(row.effective_cost) }}
          freshness={freshness}
        />
      ),
    },
    {
      key: 'items',
      header: 'Line items',
      numeric: true,
      render: (row) => row.line_items,
    },
  ];

  return (
    <section aria-label="Allocation">
      <StateBoundary state={state}>
        <label data-testid="allocation-key">
          <span>Group by tag</span>
          <select
            value={tag}
            onChange={(event) => {
              setTag(event.target.value);
            }}
          >
            {SUGGESTED.map((key) => (
              <option key={key} value={key}>
                {key}
              </option>
            ))}
          </select>
        </label>

        <p data-testid="allocation-gap">
          {unallocated
            ? `${(share * 100).toFixed(1)} percent of this period is not attributed to any ${tag}`
            : `Every charge in this period carries a ${tag}`}
        </p>

        {/* The shape before the detail. Which owners the money is on is a question a table
            of twenty rows answers slowly and a ranked bar answers at once, and the row
            nobody tagged has to be in the same picture as the ones somebody did: shown
            separately it reads as a footnote, and it is often the largest row on the
            screen. Hollow rather than filled, because it is real measured money that
            belongs to no owner. */}
        <RankedBars
          points={rows.map((row) => ({
            label: row.name === UNALLOCATED ? 'nobody tagged this' : row.name,
            value: money(row.effective_cost),
            isGap: row.name === UNALLOCATED,
          }))}
          format={(value) => `$${value.toLocaleString('en-GB', { maximumFractionDigits: 0 })}`}
          provenance="measured"
          restLabel="smaller owners"
        />

        <DataTable
          rows={rows}
          columns={columns}
          rowKey={(row) => row.name}
          caption={`${String(rows.length)} groups, largest first, including what nobody tagged`}
        />
      </StateBoundary>
    </section>
  );
}
