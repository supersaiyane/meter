import { useMemo, type ReactNode } from 'react';

import { useCostByAccount, useCostExplore, useRecommendations } from '../api/queries';
import { BudgetBar } from '../components/BudgetBar';
import { KpiTile, StackedArea, StackedBar } from '../components/charts';
import { RankedBars } from '../components/RankedBars';
import { StateBoundary } from '../components/StateBoundary';
import { Link } from '../shell/links';
import { useReportMeta } from '../shell/metaRegistry';
import { bucketLabel, signedDollars } from './exploreModel';
import { chartOf } from './forecastModel';
import { Panel } from './OverviewParts';
import { exploreQuery, stacked } from './exploreSeries';
import { percent, savingsByCategory, topMovers, wholeDollars } from './overviewKpis';
import { surfaceStateFor } from './surfaceStateFor';
import { useOverviewFigures } from './useOverviewFigures';

/**
 * The Executive dashboard, FEAT-070 and P8 spec section 5.8: where the money is going, whether
 * it is inside the budget, and where it could come back from, with the charts the owner chose
 * on 2026-10-05.
 */

/** Services named in the twelve month chart before the rest are summed. */
const SERVICES_KEPT = 6;
/** Movers named, the largest change either way first. */
const MOVERS_SHOWN = 3;
/** Accounts ranked, as chosen. */
const ACCOUNTS_SHOWN = 10;

const TWELVE_MONTHS = exploreQuery({ period: '12m', granularity: 'monthly' });

export function OverviewExecutive({ meterCost }: { readonly meterCost: ReactNode }) {
  const figures = useOverviewFigures();
  const movers = topMovers(figures.monthView, MOVERS_SHOWN);

  const year = useCostExplore(TWELVE_MONTHS, { title: 'Effective cost by service, 12 months' });
  useReportMeta('overview-year', year.data?.meta);
  const yearState = surfaceStateFor(year, year.data?.meta, 1, 'none', 'cost_focus_daily');
  const yearShape = useMemo(
    () => stacked(year.data?.data, SERVICES_KEPT, 'All other services'),
    [year.data],
  );

  const accounts = useCostByAccount();
  const accountEnvelope = accounts.data?.data;
  useReportMeta('overview-accounts', accountEnvelope?.meta);
  const accountRows = accountEnvelope?.data ?? [];
  const accountsState = surfaceStateFor(
    accounts,
    accountEnvelope?.meta,
    accountRows.length,
    'none',
    'cost_focus_daily',
  );

  const recommendations = useRecommendations();
  const recommendationEnvelope = recommendations.data?.data;
  useReportMeta('overview-recommendations', recommendationEnvelope?.meta);
  const categories = useMemo(
    () => savingsByCategory(recommendationEnvelope?.data.recommendations ?? []),
    [recommendationEnvelope],
  );
  const savingsState = surfaceStateFor(
    recommendations,
    recommendationEnvelope?.meta,
    categories.length,
    'none',
    'recommendation',
  );

  const month = figures.forecast === undefined ? null : chartOf(figures.forecast);

  return (
    <>
      <section data-testid="overview-kpis" aria-label="Key figures">
        <KpiTile
          label="Effective Cost to date"
          href="/analyze/explorer"
          provenance="measured"
          format={wholeDollars}
          points={[]}
          state={figures.cost.state}
          {...figures.cost.facts}
        />
        <KpiTile
          label="Forecast to month end"
          href="/plan/forecasts"
          provenance="forecast"
          format={wholeDollars}
          points={[]}
          state={figures.forecastKpi.state}
          {...figures.forecastKpi.facts}
        />
        <KpiTile
          label="Budget consumed against time elapsed"
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
          label="Cost allocated"
          href="/analyze/allocation"
          provenance="measured"
          format={percent}
          points={[]}
          state={figures.allocated.state}
          {...figures.allocated.facts}
        />
        <section
          className="meter-kpi meter-panel"
          aria-label="Top movers"
          data-testid="kpi-tile"
          data-provenance="measured"
        >
          <h3>
            <Link to="/analyze/explorer">Top movers</Link>{' '}
            <span data-testid="kpi-provenance">Measured</span>
          </h3>
          <StateBoundary state={figures.monthState} coverageShownElsewhere>
            {movers.length === 0 ? (
              <p data-testid="kpi-note">Nothing to compare against the same days last month</p>
            ) : (
              <ol data-testid="overview-movers">
                {movers.map((mover) => (
                  <li key={mover.name}>
                    <span>{mover.name}</span>{' '}
                    <span className="meter-numeral">{signedDollars(mover.change)}</span>
                  </li>
                ))}
              </ol>
            )}
          </StateBoundary>
          <p data-testid="kpi-formula">
            The services whose Effective Cost moved most against {figures.cost.facts.period},
            either way
          </p>
        </section>
        {meterCost}
      </section>

      <div data-testid="overview-row" data-columns="wide-narrow">
        <Panel
          id="year"
          title="Effective Cost by service, 12 months"
          href={`/analyze/explorer?${TWELVE_MONTHS}`}
        >
          <StateBoundary state={yearState} coverageShownElsewhere>
            <StackedBar
              categories={yearShape.periods.map((month) => bucketLabel(month, 'monthly'))}
              series={yearShape.series.map((one) => ({
                key: one.key,
                label: one.label,
                provenance: 'measured' as const,
                values: one.values.map((value) => value ?? 0),
              }))}
              label="Effective cost by service, month by month"
              format={wholeDollars}
              categoryName="Month"
            />
          </StateBoundary>
        </Panel>
        <Panel id="month" title="This month against the forecast" href="/plan/forecasts">
          <StateBoundary state={figures.forecastState} coverageShownElsewhere>
            {month === null ? null : (
              <StackedArea
                periods={month.periods}
                series={month.series}
                forecast={month.band}
                label="Effective cost billed to date, then the forecast's range to the month end"
                format={wholeDollars}
              />
            )}
          </StateBoundary>
        </Panel>
      </div>

      <div data-testid="overview-row" data-columns="two">
        <Panel id="accounts" title="Top 10 accounts" href="/analyze/explorer?group_by=account">
          <StateBoundary state={accountsState} coverageShownElsewhere>
            <RankedBars
              points={accountRows.map((row) => ({
                label: row.name,
                value: Number(row.effective_cost),
              }))}
              provenance="measured"
              format={wholeDollars}
              limit={ACCOUNTS_SHOWN}
              restLabel="All other accounts"
            />
          </StateBoundary>
        </Panel>
        <Panel id="savings" title="Savings available by category" href="/optimize">
          <p data-testid="overview-caption">
            Estimated monthly savings of the open recommendations. Modelled, and never added to
            what was realized, which is on its own screen.
          </p>
          <StateBoundary state={savingsState} coverageShownElsewhere>
            <RankedBars
              points={categories}
              provenance="modelled"
              format={wholeDollars}
              restLabel="All other categories"
            />
          </StateBoundary>
        </Panel>
      </div>
    </>
  );
}
