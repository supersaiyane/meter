import { useMemo, type ReactNode } from 'react';

import { useCostCommitments, useCostExplore } from '../api/queries';
import type { ApiCostSlice } from '../api/types';
import { BudgetBar } from '../components/BudgetBar';
import { KpiTile } from '../components/charts';
import { DataTable } from '../components/DataTable';
import { RankedBars } from '../components/RankedBars';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { Link } from '../shell/links';
import { useReportMeta } from '../shell/metaRegistry';
import { dollars } from './exploreModel';
import { AnomaliesPanel, DailyCostChart, Panel, RecommendationsPanel } from './OverviewParts';
import {
  ALLOCATION_TAG,
  commitmentCoverage,
  exploreQuery,
  lastDays,
  percent,
  rankedRows,
  stacked,
  wholeDollars,
} from './overviewKpis';
import { surfaceStateFor } from './surfaceStateFor';
import { useOverviewFigures } from './useOverviewFigures';

/**
 * The FinOps practitioner's dashboard, as drawn on 2026-10-05 in
 * `docs/design/2026-10-05-overview-frosted-ledger.jpg`. FEAT-070.
 *
 * Every figure is read through the hook of the screen that owns it, and every panel links there.
 * A tile whose data was not collected says so, and one the data cannot support says why, and
 * neither shows a number.
 */

/** Days in the daily chart, as drawn. */
const DAILY_DAYS = 30;
/** Services named before the rest are summed, as drawn: the top six and everything else. */
const SERVICES_SHOWN = 6;
/** Categories the daily chart names before folding the rest into one layer. */
const CATEGORIES_KEPT = 4;
/** Anomalies and recommendations shown, as drawn. */
const ANOMALIES_SHOWN = 3;
const RECOMMENDATIONS_SHOWN = 3;

const UNALLOCATED = 'unallocated';

function teamName(slice: ApiCostSlice): string {
  return slice.name === UNALLOCATED ? 'Unallocated' : slice.name;
}

export function OverviewFinOps({ meterCost }: { readonly meterCost: ReactNode }) {
  const figures = useOverviewFigures();

  const commitments = useCostCommitments();
  const commitmentEnvelope = commitments.data?.data;
  useReportMeta('overview-commitments', commitmentEnvelope?.meta);
  const commitmentState = surfaceStateFor(
    commitments,
    commitmentEnvelope?.meta,
    1,
    'none',
    'commitment_use',
  );

  const window = useMemo(() => lastDays(DAILY_DAYS, new Date()), []);
  const dailyQuery = exploreQuery({
    group_by: 'service_category',
    period: 'custom',
    start: window.start,
    end: window.end,
  });
  const daily = useCostExplore(dailyQuery, {
    title: 'Daily effective cost by service category, last 30 days',
  });
  useReportMeta('overview-daily', daily.data?.meta);
  const dailyState = surfaceStateFor(daily, daily.data?.meta, 1, 'none', 'cost_focus_daily');
  const shape = useMemo(
    () => stacked(daily.data?.data, CATEGORIES_KEPT, 'Everything else'),
    [daily.data],
  );
  const dailyTotals = shape.periods.map((_, index) =>
    shape.series.reduce((total, series) => total + (series.values[index] ?? 0), 0),
  );

  const slices = figures.slices ?? [];
  const total = slices.reduce((sum, slice) => sum + Number(slice.effective_cost), 0);
  const teamColumns: readonly Column<ApiCostSlice>[] = [
    { key: 'team', header: 'Team', render: teamName },
    {
      key: 'cost',
      header: 'Effective cost',
      numeric: true,
      render: (slice) => dollars(Number(slice.effective_cost)),
    },
    {
      key: 'share',
      header: 'Share',
      numeric: true,
      render: (slice) =>
        total === 0 ? 'Not available' : percent(Number(slice.effective_cost) / total),
    },
  ];

  return (
    <>
      <section data-testid="overview-kpis" aria-label="Key figures">
        <KpiTile
          label="Effective Cost"
          href="/analyze/explorer"
          provenance="measured"
          format={wholeDollars}
          points={dailyTotals}
          state={figures.cost.state}
          {...figures.cost.facts}
        />
        <KpiTile
          label="Forecast, month end"
          href="/plan/forecasts"
          provenance="forecast"
          format={wholeDollars}
          points={[]}
          state={figures.forecastKpi.state}
          {...figures.forecastKpi.facts}
        />
        <KpiTile
          label="Budget consumed"
          href="/plan/budgets"
          provenance="measured"
          format={percent}
          points={[]}
          state={figures.budget.state}
          {...figures.budget.facts}
        >
          {figures.worst === null ? null : <BudgetBar budget={figures.worst} />}
        </KpiTile>
        <KpiTile
          label="Effective savings rate"
          href="/optimize/commitments"
          provenance="measured"
          format={percent}
          points={[]}
          state={figures.savings.state}
          {...figures.savings.facts}
        />
        <KpiTile
          label="Commitment coverage"
          href="/optimize/commitments"
          provenance="measured"
          format={percent}
          points={[]}
          state={commitmentState}
          {...commitmentCoverage(commitmentEnvelope?.data)}
        />
        <KpiTile
          label="Cost allocated"
          href="/analyze/allocation"
          provenance="measured"
          format={percent}
          points={[]}
          state={figures.allocated.state}
          {...figures.allocated.facts}
        />
        {meterCost}
      </section>

      <div data-testid="overview-row" data-columns="wide-narrow">
        <Panel id="daily" title="Daily Effective Cost" href={`/analyze/explorer?${dailyQuery}`}>
          <p data-testid="overview-caption">
            The last 30 days by service category, with the daily budget pace. The forecast is a
            running total for the month, so it is the month end tile rather than a line here.
          </p>
          <StateBoundary state={dailyState} coverageShownElsewhere>
            <DailyCostChart
              shape={shape}
              budget={figures.estate}
              label="Daily effective cost by service category"
            />
            {figures.estate === null && figures.budgetsRead ? (
              <p data-testid="overview-no-pace">
                No single budget covers every account, so there is no daily budget pace to draw.
              </p>
            ) : null}
          </StateBoundary>
        </Panel>
        <Panel id="services" title="Effective Cost by service" href="/analyze/explorer">
          <p data-testid="overview-caption">Month to date, the top six and the rest</p>
          <StateBoundary state={figures.monthState} coverageShownElsewhere>
            <RankedBars
              points={rankedRows(figures.monthView)}
              provenance="measured"
              format={wholeDollars}
              limit={SERVICES_SHOWN}
              restLabel="All other services"
            />
          </StateBoundary>
        </Panel>
      </div>

      <div data-testid="overview-row" data-columns="three">
        <AnomaliesPanel limit={ANOMALIES_SHOWN} />
        <RecommendationsPanel limit={RECOMMENDATIONS_SHOWN} />
        <Panel id="scheduled" title="Scheduled reports" href="/report/scheduled">
          <p data-testid="overview-scheduled-arrives">
            Not built yet, arrives with <Link to="/report/scheduled">P8</Link>
          </p>
        </Panel>
      </div>

      <Panel id="showback" title="Showback by team" href="/analyze/allocation">
        <p data-testid="overview-caption">
          Effective cost this period, allocated by the {ALLOCATION_TAG} tag. Unallocated is
          shown, never hidden.
        </p>
        <StateBoundary state={figures.allocationState} coverageShownElsewhere>
          <DataTable
            rows={slices}
            columns={teamColumns}
            rowKey={(slice) => slice.name}
            caption={`Showback by the ${ALLOCATION_TAG} tag`}
          />
        </StateBoundary>
      </Panel>
    </>
  );
}
