import type { ReactNode } from 'react';

import { useCostAnomalies, useRecommendations, useSchedules } from '../api/queries';
import type { ApiBudget, ApiSchedule } from '../api/types';
import { StackedArea } from '../components/charts';
import { wasteClassName } from '../components/displayNames';
import { DensityContext } from '../components/density';
import { Figure } from '../components/Figure';
import { StateBoundary } from '../components/StateBoundary';
import { Link } from '../shell/links';
import { useReportMeta } from '../shell/metaRegistry';
import { signedDollars } from './exploreModel';
import { type Stacked } from './exploreSeries';
import { changedAt } from './libraryModel';
import { dailyPace, dayName, openRecommendations, wholeDollars } from './overviewKpis';
import { cadenceWords, listState } from './scheduleModel';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * The pieces the Overview's three dashboards share, FEAT-070. Each panel's heading links to the
 * screen that owns what it shows, because the Overview owns no figure of its own.
 */

export interface PanelProps {
  readonly id: string;
  readonly title: string;
  readonly href: string;
  readonly children: ReactNode;
}

export function Panel({ id, title, href, children }: PanelProps) {
  return (
    <section data-testid={`overview-${id}`} aria-label={title} className="meter-panel">
      <h3>
        <Link to={href}>{title}</Link>
      </h3>
      {children}
    </section>
  );
}

export interface DailyCostChartProps {
  readonly shape: Stacked;
  /** The one budget covering every account, whose daily allowance is drawn, or null. */
  readonly budget: ApiBudget | null;
  readonly label: string;
}

/**
 * Spend by day, stacked, with the estate budget's daily allowance on the same scale, as drawn on
 * 2026-10-05. The drawing carried the forecast on into the month as well, and it is not drawn
 * here: the forecast route's interval is a running total for the month, and a daily interval
 * cut from it would be a number nothing computed. It is the month end tile and the Executive
 * dashboard's chart instead.
 */
export function DailyCostChart({ shape, budget, label }: DailyCostChartProps) {
  const pace = dailyPace(budget, shape.periods);
  return (
    <StackedArea
      periods={shape.periods}
      series={shape.series.map((one) => ({ ...one, provenance: 'measured' as const }))}
      {...(pace === undefined ? {} : { pace })}
      label={label}
      format={wholeDollars}
    />
  );
}

/** The anomalies with the largest excess over their baseline, worst first. */
export function AnomaliesPanel({ limit }: { readonly limit?: number }) {
  const anomalies = useCostAnomalies();
  const envelope = anomalies.data?.data;
  useReportMeta('overview-anomalies', envelope?.meta);
  const rows = envelope?.data.anomalies ?? [];
  // Ready once the answer is in, even with nothing in it: no anomaly is news, not a filter that
  // matched nothing.
  const state = surfaceStateFor(anomalies, envelope?.meta, 1, 'none', 'cost_focus_daily');
  const shown = [...rows]
    .sort((left, right) => Number(right.delta) - Number(left.delta))
    .slice(0, limit ?? rows.length);
  return (
    <Panel id="anomalies" title="Anomalies" href="/analyze/anomalies">
      <StateBoundary state={state} coverageShownElsewhere>
        {shown.length === 0 ? (
          <p data-testid="overview-anomalies-none">No anomalies this period</p>
        ) : (
          <ul data-testid="overview-anomaly-list">
            {shown.map((one) => (
              <li key={`${one.account_id} ${one.service_name} ${one.day}`}>
                <span data-testid="overview-anomaly-service">{one.service_name}</span>
                <span>
                  {one.account_id}, {dayName(one.day)}, {one.severity.toLowerCase()}
                </span>
                <span className="meter-numeral">{signedDollars(Number(one.delta))}</span>
              </li>
            ))}
          </ul>
        )}
      </StateBoundary>
    </Panel>
  );
}

/**
 * The open recommendations worth the most each month, as drawn. Every saving is modelled and
 * marked so, because an estimate that looks measured is the one claim this product cannot get
 * wrong. Ranked by money, the order the recommendations screen uses.
 */
export function RecommendationsPanel({ limit }: { readonly limit: number }) {
  const recommendations = useRecommendations();
  const envelope = recommendations.data?.data;
  useReportMeta('overview-recommendations', envelope?.meta);
  const rows = openRecommendations(envelope?.data.recommendations ?? []);
  const state = surfaceStateFor(recommendations, envelope?.meta, 1, 'none', 'recommendation');
  const top = [...rows]
    .sort(
      (left, right) =>
        Number(right.estimated_monthly_saving) - Number(left.estimated_monthly_saving),
    )
    .slice(0, limit);
  const freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };
  return (
    <Panel id="recommendations" title="Top recommendations" href="/optimize">
      <p data-testid="overview-caption">Modelled monthly savings, the largest first</p>
      <StateBoundary state={state} coverageShownElsewhere>
        {top.length === 0 ? (
          <p data-testid="overview-recommendations-none">No recommendation is open</p>
        ) : (
          // The trust strip above the page carries the freshness, as it does for a dense table, so
          // each saving keeps its provenance in words and drops its own timestamps.
          <DensityContext.Provider value>
            <ul data-testid="overview-recommendation-list">
              {top.map((one) => (
                <li key={one.recommendation_id}>
                  <span data-testid="overview-recommendation-name">
                    {wasteClassName(one.waste_class)}
                  </span>
                  <span>
                    {one.resource_id}, {one.account_id}, {one.confidence.toLowerCase()}{' '}
                    confidence
                  </span>
                  <Figure
                    value={{ kind: 'modelled', amount: Number(one.estimated_monthly_saving) }}
                    freshness={freshness}
                  />
                </li>
              ))}
            </ul>
          </DensityContext.Provider>
        )}
      </StateBoundary>
    </Panel>
  );
}

/** A paused schedule first, then the next to run. */
function byAttention(left: ApiSchedule, right: ApiSchedule): number {
  if (left.enabled !== right.enabled) {
    return left.enabled ? 1 : -1;
  }
  return left.next_run_at.localeCompare(right.next_run_at);
}

/**
 * The reader's scheduled reports, FEAT-069: a paused one first and says so, because a report
 * that will not arrive is the one its reader most needs telling about, then the next to run.
 */
export function ScheduledPanel({ limit }: { readonly limit: number }) {
  const schedules = useSchedules();
  const envelope = schedules.data;
  useReportMeta('overview-scheduled', envelope?.meta);
  // Ready once the answer is in, even with nothing in it, as the anomalies are.
  const state = listState(
    surfaceStateFor(schedules, envelope?.meta, 1, 'none', 'report_schedules'),
  );
  const shown = [...(envelope?.data.schedules ?? [])].sort(byAttention).slice(0, limit);
  return (
    <Panel id="scheduled" title="Scheduled reports" href="/report/scheduled">
      <StateBoundary state={state} coverageShownElsewhere>
        {shown.length === 0 ? (
          <p data-testid="overview-scheduled-none">
            None yet. A saved view is scheduled from the{' '}
            <Link to="/report/library">Report Library</Link>.
          </p>
        ) : (
          <ul data-testid="overview-scheduled-list">
            {shown.map((one) => (
              <li key={one.schedule_id}>
                <span>{one.view_name ?? 'A view you can no longer open'}</span>
                <span>{cadenceWords(one.cadence)}</span>
                {one.enabled ? (
                  <time className="meter-numeral" dateTime={one.next_run_at}>
                    {changedAt(one.next_run_at)}
                  </time>
                ) : (
                  <span>Paused</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </StateBoundary>
    </Panel>
  );
}
