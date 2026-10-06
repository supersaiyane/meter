import { useMemo, type ReactNode } from 'react';

import {
  useCostExplore,
  useQueryFindings,
  useQueryGroups,
  useQuerySurfaces,
  useRecommendations,
} from '../api/queries';
import type {
  ApiQueryFinding,
  ApiQueryGroup,
  ApiRecommendation,
  ApiSurfaceInstance,
} from '../api/types';
import { Treemap } from '../components/charts';
import { DataTable } from '../components/DataTable';
import { wasteClassName } from '../components/displayNames';
import { Figure } from '../components/Figure';
import { SeverityBadge, type Severity } from '../components/SeverityBadge';
import { StateBoundary } from '../components/StateBoundary';
import { TopActions } from '../components/TopActions';
import type { Column } from '../components/tableConfig';
import { Link } from '../shell/links';
import { useReportMeta } from '../shell/metaRegistry';
import { AnomaliesPanel, DailyCostChart, Panel } from './OverviewParts';
import {
  exploreQuery,
  lastDays,
  MONTH_BY_SERVICE,
  openRecommendations,
  rankedRows,
  RIGHTSIZING,
  stacked,
  wholeDollars,
} from './overviewKpis';
import { severityOf } from './querySeverity';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * The Engineering lead's dashboard, FEAT-070 and P8 spec section 5.8: daily cost by service, the
 * anomalies, the rightsizing and the query cost of the dashboards, all in the scope the reader
 * chose. Narrowed by the account picker like every other figure, so a team reading its own
 * account reads its own estate.
 */

const DAILY_DAYS = 30;
const SERVICES_KEPT = 6;
const TOP_FINDINGS = 3;

/** Worst first, which is the order someone reads a severity summary in. */
const SEVERITY_ORDER: readonly Severity[] = [5, 4, 3, 2, 1];

/** The costliest cause, picked rather than summed, so it cannot disagree with its screen. */
function largestGroup(groups: readonly ApiQueryGroup[]): ApiQueryGroup | null {
  let worst: ApiQueryGroup | null = null;
  for (const group of groups) {
    if (worst === null || Number(group.monthly_cost) > Number(worst.monthly_cost)) {
      worst = group;
    }
  }
  return worst;
}

/** Why each unreadable surface refused, counted by typed cause. */
function refusalsBy(instances: readonly ApiSurfaceInstance[]): ReadonlyMap<string, number> {
  const causes = new Map<string, number>();
  for (const instance of instances) {
    if (instance.reachable) continue;
    const cause = instance.unreachable_reason ?? 'Unknown';
    causes.set(cause, (causes.get(cause) ?? 0) + 1);
  }
  return causes;
}

function countBySeverity(rows: readonly ApiQueryFinding[]): ReadonlyMap<Severity, number> {
  const counts = new Map<Severity, number>();
  for (const row of rows) {
    const level = severityOf(row);
    counts.set(level, (counts.get(level) ?? 0) + 1);
  }
  return counts;
}

export function OverviewEngineering({ meterCost }: { readonly meterCost: ReactNode }) {
  const window = useMemo(() => lastDays(DAILY_DAYS, new Date()), []);
  const dailyQuery = exploreQuery({ period: 'custom', start: window.start, end: window.end });
  const daily = useCostExplore(dailyQuery, {
    title: 'Daily effective cost by service, last 30 days',
  });
  useReportMeta('overview-daily-services', daily.data?.meta);
  const dailyState = surfaceStateFor(daily, daily.data?.meta, 1, 'none', 'cost_focus_daily');
  const shape = useMemo(
    () => stacked(daily.data?.data, SERVICES_KEPT, 'All other services'),
    [daily.data],
  );

  const month = useCostExplore(MONTH_BY_SERVICE, {
    title: 'Effective cost by service, month to date',
  });
  useReportMeta('overview-month', month.data?.meta);
  const monthState = surfaceStateFor(month, month.data?.meta, 1, 'none', 'cost_focus_daily');

  const recommendations = useRecommendations();
  const recommendationEnvelope = recommendations.data?.data;
  useReportMeta('overview-recommendations', recommendationEnvelope?.meta);
  const rightsizing = useMemo(
    () =>
      openRecommendations(recommendationEnvelope?.data.recommendations ?? []).filter((one) =>
        RIGHTSIZING.has(one.waste_class),
      ),
    [recommendationEnvelope],
  );
  const rightsizingState = surfaceStateFor(
    recommendations,
    recommendationEnvelope?.meta,
    rightsizing.length,
    'none',
    'recommendation',
  );

  const actionsState = surfaceStateFor(
    recommendations,
    recommendationEnvelope?.meta,
    recommendationEnvelope?.data.recommendations.length ?? 0,
    'none',
    'recommendation',
  );

  const findings = useQueryFindings();
  const findingsEnvelope = findings.data?.data;
  const rows = useMemo(() => findingsEnvelope?.data ?? [], [findingsEnvelope]);
  useReportMeta('overview-query-findings', findingsEnvelope?.meta);
  const findingsState = surfaceStateFor(
    findings,
    findingsEnvelope?.meta,
    rows.length,
    'none',
    'query_audit',
  );
  const groups = useQueryGroups();
  const groupRows = useMemo(() => groups.data?.data.data ?? [], [groups.data]);
  const groupsState = surfaceStateFor(
    groups,
    groups.data?.data.meta,
    groupRows.length,
    'none',
    'query_audit',
  );
  const worst = useMemo(() => largestGroup(groupRows), [groupRows]);
  const surfaces = useQuerySurfaces();
  const surfaceRows = useMemo(() => surfaces.data?.data.data ?? [], [surfaces.data]);
  const surfacesState = surfaceStateFor(
    surfaces,
    surfaces.data?.data.meta,
    surfaceRows.length,
    'none',
    'query_audit',
  );
  const readable = surfaceRows.filter((row) => row.reachable).length;
  const refusals = useMemo(() => refusalsBy(surfaceRows), [surfaceRows]);
  const counts = useMemo(() => countBySeverity(rows), [rows]);
  const top = rows.slice(0, TOP_FINDINGS);
  const freshness = {
    asOf: new Date(findingsEnvelope?.meta.as_of ?? 0),
    collectedAt: new Date(findingsEnvelope?.meta.collected_at ?? 0),
  };
  const recommendationFreshness = {
    asOf: new Date(recommendationEnvelope?.meta.as_of ?? 0),
    collectedAt: new Date(recommendationEnvelope?.meta.collected_at ?? 0),
  };

  const findingColumns: readonly Column<ApiQueryFinding>[] = [
    {
      key: 'severity',
      header: 'Severity',
      render: (row) => <SeverityBadge level={severityOf(row)} />,
    },
    {
      key: 'finding',
      header: 'Finding',
      render: (row) => (
        <Link to={`/govern/query-cost/findings/${row.finding_id}`}>
          {row.dashboard_title}, {row.panel_title}
        </Link>
      ),
    },
    {
      key: 'monthly',
      header: 'Monthly',
      numeric: true,
      render: (row) => (
        <Figure
          value={
            row.provenance === 'measured'
              ? { kind: 'measured', amount: Number(row.monthly_cost) }
              : { kind: 'modelled', amount: Number(row.monthly_cost) }
          }
          freshness={freshness}
        />
      ),
    },
    { key: 'owner', header: 'Owner', render: (row) => row.owner ?? 'unattributed' },
  ];
  const rightsizingColumns: readonly Column<ApiRecommendation>[] = [
    { key: 'class', header: 'Change', render: (one) => wasteClassName(one.waste_class) },
    { key: 'resource', header: 'Resource', render: (one) => one.resource_id },
    { key: 'where', header: 'Where', render: (one) => `${one.account_id}, ${one.region_id}` },
    {
      key: 'saving',
      header: 'Monthly saving',
      numeric: true,
      render: (one) => (
        <Figure
          value={{ kind: 'modelled', amount: Number(one.estimated_monthly_saving) }}
          freshness={recommendationFreshness}
        />
      ),
    },
    { key: 'confidence', header: 'Confidence', render: (one) => one.confidence.toLowerCase() },
  ];

  return (
    <>
      {/* Constraint 7: Meter's own cost is on the front page, whichever dashboard that is. */}
      <section data-testid="overview-kpis" aria-label="Key figures">
        {meterCost}
      </section>

      <div data-testid="overview-row" data-columns="wide-narrow">
        <Panel
          id="daily-services"
          title="Daily Effective Cost by service"
          href={`/analyze/explorer?${dailyQuery}`}
        >
          <StateBoundary state={dailyState} coverageShownElsewhere>
            <DailyCostChart
              shape={shape}
              budget={null}
              label="Daily effective cost by service, the last 30 days"
            />
          </StateBoundary>
        </Panel>
        <Panel id="treemap" title="Where this month went" href="/analyze/explorer">
          <StateBoundary state={monthState} coverageShownElsewhere>
            <Treemap
              items={rankedRows(month.data?.data)}
              provenance="measured"
              label="Effective cost by service, month to date"
              format={wholeDollars}
            />
          </StateBoundary>
        </Panel>
      </div>

      <div data-testid="overview-row" data-columns="wide-narrow">
        <Panel id="rightsizing" title="Rightsizing" href="/optimize">
          <StateBoundary state={rightsizingState}>
            <DataTable
              rows={rightsizing}
              columns={rightsizingColumns}
              rowKey={(one) => one.recommendation_id}
              caption="Resources whose size or type could change, estimated and modelled"
            />
          </StateBoundary>
        </Panel>
        <AnomaliesPanel />
      </div>

      {/* FEAT-052's Top actions, ranked by money and saying what each costs if it is wrong. It
          moved here from the single front page with FEAT-070: the FinOps dashboard draws its
          own short list, as drawn, and this is where somebody acts on them. */}
      <StateBoundary state={actionsState}>
        <TopActions
          recommendations={recommendationEnvelope?.data.recommendations ?? []}
          freshness={recommendationFreshness}
        />
      </StateBoundary>

      <section data-testid="home-summary" aria-label="Query cost of the dashboards">
        <div data-testid="home-tile" aria-label="Open findings">
          <h3>
            <Link to="/govern/query-cost">Open findings</Link>
          </h3>
          <StateBoundary state={findingsState} coverageShownElsewhere>
            <p data-testid="home-count">{rows.length}</p>
            <ul data-testid="home-severity-key">
              {SEVERITY_ORDER.filter((level) => counts.has(level)).map((level) => (
                <li key={level}>
                  <SeverityBadge level={level} />
                  <span data-testid="home-severity-count">{counts.get(level)}</span>
                </li>
              ))}
            </ul>
          </StateBoundary>
        </div>

        <div data-testid="home-tile" aria-label="Largest cause">
          <h3>
            <Link to="/govern/query-cost">Largest cause</Link>
          </h3>
          <StateBoundary state={groupsState} coverageShownElsewhere>
            {worst ? (
              <>
                <p data-testid="home-tile-note">{worst.label}</p>
                {/* Modelled: a group sums findings whose provenance differs. */}
                <Figure
                  value={{ kind: 'modelled', amount: Number(worst.monthly_cost) }}
                  freshness={{
                    asOf: new Date(worst.as_of),
                    collectedAt: new Date(worst.collected_at),
                  }}
                  label="Largest cause"
                />
                <p data-testid="home-tile-note">{worst.findings} findings, one fault</p>
              </>
            ) : null}
          </StateBoundary>
        </div>

        <div data-testid="home-tile" aria-label="Sources under audit">
          <h3>
            <Link to="/govern/query-cost/surfaces">Sources under audit</Link>
          </h3>
          <StateBoundary state={surfacesState} coverageShownElsewhere>
            {/* Always a ratio: a surface Meter could not read is not one with nothing in it. */}
            <p data-testid="home-count">
              {readable} of {surfaceRows.length}
            </p>
            <ul data-testid="home-refusals">
              {[...refusals].map(([cause, count]) => (
                <li key={cause}>
                  <span className="meter-failure">{cause}</span>
                  <span data-testid="home-severity-count">{count}</span>
                </li>
              ))}
            </ul>
          </StateBoundary>
        </div>
      </section>

      <Panel id="findings" title="Top findings by dollar" href="/govern/query-cost">
        <StateBoundary state={findingsState}>
          <DataTable
            rows={top}
            columns={findingColumns}
            rowKey={(row) => row.finding_id}
            caption={`The ${String(top.length)} most expensive, of ${String(rows.length)}`}
          />
        </StateBoundary>
      </Panel>
    </>
  );
}
