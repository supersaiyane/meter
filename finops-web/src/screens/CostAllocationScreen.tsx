import { useMemo } from 'react';

import { useCostAllocation, useCostExplore } from '../api/queries';
import { ChartPanel } from '../components/ChartPanel';
import { StackedArea, Treemap } from '../components/charts';
import { DataTable } from '../components/DataTable';
import { Figure } from '../components/Figure';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useFilters } from '../shell/filters';
import { useReportMeta } from '../shell/metaRegistry';
import { ALLOCATION_FILTERS } from '../shell/sections';
import { exploreQuery, stacked } from './exploreSeries';
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

function dollars(value: number): string {
  return `$${value.toLocaleString('en-GB', { maximumFractionDigits: 0 })}`;
}

/** Owners drawn by name in the trend. Every other owner is one layer, so nothing is dropped. */
const OWNERS_KEPT = 6;

export function CostAllocationScreen() {
  const { values, set } = useFilters(ALLOCATION_FILTERS);
  // The key in the address, so a link can land grouped by it, and the first suggestion when
  // it names none. A key that is not a suggestion is still offered, so the control always
  // shows the grouping in force.
  const tag = values.tag === '' ? SUGGESTED[0] : values.tag;
  const keys: readonly string[] = (SUGGESTED as readonly string[]).includes(tag)
    ? SUGGESTED
    : [...SUGGESTED, tag];
  const query = useCostAllocation(tag);
  const envelope = query.data?.data;
  const rows = useMemo(() => envelope?.data ?? [], [envelope]);

  useReportMeta('cost-allocation', envelope?.meta);
  const state = surfaceStateFor(query, envelope?.meta, rows.length, 'none', 'cost_focus');

  const freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };

  // Each month by the same tag, read the way Cost Explorer reads it. Asked only once a charge
  // this period carries the tag, because the Explorer groups only by keys it has seen, and a
  // tag nothing carries is a sentence rather than a failure.
  const tagged = rows.some((row) => row.name !== UNALLOCATED);
  const trend = useCostExplore(
    exploreQuery({ period: '6m', granularity: 'monthly', group_by: 'tag', group_by_tag: tag }),
    { enabled: tagged, title: `Effective Cost by ${tag}, six months` },
  );
  useReportMeta('cost-allocation-trend', tagged ? trend.data?.meta : undefined);
  const trendState = surfaceStateFor(trend, trend.data?.meta, 1, 'none', 'cost_focus');
  const months = useMemo(
    () => stacked(trend.data?.data, OWNERS_KEPT, `Every other ${tag}`),
    [trend.data, tag],
  );

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
          <span data-testid="allocation-unallocated">Unallocated cost</span>
        ) : (
          row.name
        ),
    },
    {
      key: 'cost',
      header: 'Effective Cost',
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
    <section aria-label="Allocation and Showback">
      <StateBoundary state={state}>
        <label data-testid="allocation-key">
          <span>Group by tag</span>
          <select
            value={tag}
            onChange={(event) => {
              set('tag', event.target.value === SUGGESTED[0] ? '' : event.target.value);
            }}
          >
            {keys.map((key) => (
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

        {/* The shape before the detail, and the row nobody tagged in the same picture as the ones
            somebody did: shown separately it reads as a footnote, and it is often the largest
            area on the screen. An outline rather than a colour, because it is real measured
            money that belongs to no owner. */}
        <div data-testid="chart-row">
          <ChartPanel
            id="allocation-share"
            title={`Whose spend it is, by ${tag}`}
            caption="This period's Effective Cost as areas, the untagged part outlined"
          >
            <Treemap
              items={rows.map((row) => ({
                label: row.name === UNALLOCATED ? 'Unallocated cost' : row.name,
                value: money(row.effective_cost),
                isGap: row.name === UNALLOCATED,
              }))}
              provenance="measured"
              label={`Effective Cost this period by ${tag}`}
              format={dollars}
            />
          </ChartPanel>
          <ChartPanel
            id="allocation-trend"
            title={`Each month, by ${tag}`}
            caption={`Effective Cost for the last six months by the ${tag} tag`}
          >
            {tagged ? (
              <StateBoundary state={trendState} coverageShownElsewhere>
                <StackedArea
                  periods={months.periods}
                  series={months.series.map((one) => ({
                    ...one,
                    provenance: 'measured' as const,
                  }))}
                  label={`Effective Cost each month by ${tag}, last six months`}
                  format={dollars}
                />
              </StateBoundary>
            ) : (
              <p data-testid="allocation-untrended">
                No charge this period carries a {tag} tag, so there is no trend by it yet
              </p>
            )}
          </ChartPanel>
        </div>

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
