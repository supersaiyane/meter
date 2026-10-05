import { useMemo } from 'react';
import { Link } from 'react-router';

import {
  useBudgets,
  useCostSummary,
  useCostTrend,
  usePlatformCost,
  useQueryFindings,
  useQueryGroups,
  useQuerySurfaces,
  useRecommendations,
} from '../api/queries';
import { grandTotal, rollUp } from './platformRollUp';
import { BarChart } from '../components/BarChart';
import { BudgetBar } from '../components/BudgetBar';
import { Figure } from '../components/Figure';
import { DataTable } from '../components/DataTable';
import { SeverityBadge, type Severity } from '../components/SeverityBadge';
import { StateBoundary } from '../components/StateBoundary';
import { TopActions } from '../components/TopActions';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { severityOf } from './querySeverity';
import { surfaceStateFor } from './surfaceStateFor';
import type {
  ApiBudget,
  ApiQueryFinding,
  ApiQueryGroup,
  ApiSurfaceInstance,
} from '../api/types';

/**
 * The front page. A trust strip above the money, per
 * `docs/13-UI-ARCHITECTURE.md` section 6.
 *
 * Three rules carry this screen.
 *
 * It owns no data of its own. Every figure is a roll up of a screen that exists
 * elsewhere, read through that screen's own hook, and every one links to it. A
 * home screen with its own query will one day disagree with the screen it
 * summarises, and a reader who catches that disagreement stops trusting both.
 *
 * An unfilled slot names the sub project that will fill it. It never renders as
 * zero, blank, or a broken panel. That is rule 5 of `docs/12-UI-DESIGN.md`
 * applied to an absence, and it is what makes this page the progress view: each
 * sub project that lands turns one named absence into a number.
 *
 * The page is ranked in three tiers, after the AWS Cloud Intelligence pattern:
 * a summary, then what to do about it, then the absences. Tier two held one panel until
 * 2026-09-26 and holds two now, Top actions above the query findings table, because the
 * first answers what to do across the whole estate and the second is the same question
 * narrowed to one sub project. The
 * absences used to be panels drawn at the same weight as the money, which meant
 * nothing on the page outranked anything else. They are one rail now. The claim
 * they make is unchanged, it just no longer outweighs the facts.
 */

export interface SlotDef {
  readonly id: string;
  readonly label: string;
  /** The screen that will own this figure. */
  readonly owns: string;
  /** The sub project that will fill it. */
  readonly arrives: string;
}

/**
 * Only the slots that are still empty. A slot leaves this list the day its sub
 * project lands, and becomes a tile above or leaves the page.
 *
 * Empty today, and the rail draws nothing while it is, rather than a heading
 * over nothing.
 */
const ABSENT: readonly SlotDef[] = [
  // Spend, trend and top movers stood here until 2026-09-20, all three claiming to
  // arrive with P1. P1 landed, and a front page still promising the thing the reader
  // can already open is worse than one that never mentioned it: it says the product
  // does not know what it has. Spend and trend became the tile below, which is what
  // this list's own comment said should happen.
  //
  // Top movers left without becoming a tile, because nothing was built for it and no
  // feature in the registry owns it. A slot naming a sub project that has shipped is a
  // promise nobody is keeping, so it is better absent than misattributed. ISS-188.
  //
  // Realized savings stood here until 2026-10-05, still saying it would arrive with
  // P3 Utilization and Rightsizing after P3 had shipped and /waste/savings was built.
  // The same failure as the P1 slots, and it left the same way.
];

/** Three. A front page summary that needs scrolling is a second screen. */
const TOP_FINDINGS = 3;

/** Worst first, which is the order someone reads a severity summary in. */
const SEVERITY_ORDER: readonly Severity[] = [5, 4, 3, 2, 1];

/**
 * The costliest cause, which is the figure ADR-0016 exists for: twelve cheap
 * panels sharing one fault outrank a single expensive one, and only an
 * aggregate can say so. Picked here rather than summed, because the server
 * already computed each group and a total this screen invented could disagree
 * with the screen it links to.
 */
function largestGroup(groups: readonly ApiQueryGroup[]): ApiQueryGroup | null {
  let worst: ApiQueryGroup | null = null;
  for (const group of groups) {
    if (worst === null || Number(group.monthly_cost) > Number(worst.monthly_cost)) {
      worst = group;
    }
  }
  return worst;
}

/**
 * Why each unreadable surface refused, counted by typed cause. A surface Meter
 * could not read is not a surface with nothing in it, so the count of readable
 * ones is always shown against the total and never on its own.
 */
function refusalsBy(instances: readonly ApiSurfaceInstance[]): ReadonlyMap<string, number> {
  const causes = new Map<string, number>();
  for (const instance of instances) {
    if (instance.reachable) continue;
    // Required when reachable is false, but a null here would otherwise render
    // as an unexplained gap rather than as the unknown it is.
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

/**
 * The absences, as one rail rather than a stack of panels. Each entry keeps its
 * own test id, its own wording and its own link, because what it claims has not
 * changed. Only its weight on the page has.
 *
 * Nothing at all when there is nothing still to arrive. A "Not yet collected"
 * heading over an empty list is a claim about an absence that does not exist.
 */
export function ArrivingRail({ slots }: { readonly slots: readonly SlotDef[] }) {
  if (slots.length === 0) return null;
  return (
    <section data-testid="home-rail" aria-label="Not yet collected">
      <h3>Not yet collected</h3>
      <ul>
        {slots.map((slot) => (
          <li key={slot.id} data-testid={`home-slot-${slot.id}`}>
            <span data-testid="home-rail-label">{slot.label}</span>
            <span data-testid="home-rail-arrives">
              not yet collected, arrives with <Link to={slot.owns}>{slot.arrives}</Link>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * The budget a reader needs to see first, which is the one furthest ahead of its own calendar.
 *
 * Not the largest limit and not the most spent: both of those rank a big healthy budget above a
 * small one that is about to blow. Ranking by how far the spend has run ahead of the period puts
 * the finding first, and a budget with no number is never the answer, because an absence cannot
 * be the worst thing on a page that has real ones on it.
 */
function mostAtRisk(budgets: readonly ApiBudget[]): ApiBudget | null {
  const ranked = budgets
    .filter((one) => one.used !== null)
    .map((one) => ({ one, ahead: Number(one.used) - Number(one.elapsed) }))
    .sort((left, right) => right.ahead - left.ahead);
  return ranked[0]?.one ?? null;
}

export function HomeScreen() {
  const cost = usePlatformCost();
  useReportMeta('platform-cost', cost.data?.meta);
  const costRows = useMemo(() => rollUp(cost.data?.data ?? []), [cost.data]);
  const grand = useMemo(() => grandTotal(costRows), [costRows]);
  const costState = surfaceStateFor(
    cost,
    cost.data?.meta,
    costRows.length,
    'none',
    'platform_cost',
  );

  // The spend screen's own hook, for the same reason the findings hook is reused
  // below: a total this screen computed could disagree with the screen it links to,
  // and a front page disagreeing with the page behind it is the one inconsistency a
  // reader always notices.
  const budgets = useBudgets();
  const budgetEnvelope = budgets.data?.data;
  const budgetRows = useMemo(() => budgetEnvelope?.data.budgets ?? [], [budgetEnvelope]);
  const worstBudget = useMemo(() => mostAtRisk(budgetRows), [budgetRows]);
  useReportMeta('home-budgets', budgetEnvelope?.meta);
  const budgetState = surfaceStateFor(
    budgets,
    budgetEnvelope?.meta,
    budgetRows.length,
    'none',
    'budgets',
  );

  const spend = useCostSummary();
  // The daily shape behind the headline. Through the cost screen's own hook, because the
  // home screen owns no data of its own: a panel with its own query will one day disagree
  // with the screen it summarises.
  const trend = useCostTrend();
  const days = trend.data?.data.data ?? [];
  const spendEnvelope = spend.data?.data;
  const summary = spendEnvelope?.data;
  const spendState = surfaceStateFor(
    spend,
    spendEnvelope?.meta,
    summary ? 1 : 0,
    'none',
    'cost_focus_daily',
  );

  // The findings screen's own hook and its own query key, so the two can never
  // disagree. Read once here and shared, rather than called in two places.
  const findings = useQueryFindings();
  const envelope = findings.data?.data;
  const rows = useMemo(() => envelope?.data ?? [], [envelope]);
  useReportMeta('home-query-findings', envelope?.meta);
  const findingsState = surfaceStateFor(
    findings,
    envelope?.meta,
    rows.length,
    'none',
    'query_audit',
  );

  // The recommendations screen's own hook, for FEAT-052's Top actions panel. Home still
  // owns no query: this is the same key `/waste` uses, so the panel and the screen it
  // summarises cannot disagree about what is open or about how it is ranked.
  //
  // It summarises the rows that hook returned rather than asking for its own slice, which
  // means the no regret group is drawn from the same two hundred the screen shows. A
  // dedicated query would have found the small reversible findings that fall past that
  // limit, and would also have been the second answer this page is built to avoid.
  const recommendations = useRecommendations();
  const recommendationEnvelope = recommendations.data?.data;
  const actionRows = useMemo(
    () => recommendationEnvelope?.data.recommendations ?? [],
    [recommendationEnvelope],
  );
  useReportMeta('home-recommendations', recommendationEnvelope?.meta);
  const actionsState = surfaceStateFor(
    recommendations,
    recommendationEnvelope?.meta,
    actionRows.length,
    'none',
    'recommendation',
  );

  // The groups screen's own hook and the surfaces screen's own hook. Home still
  // owns no query: each of these belongs to a screen that already asks for it,
  // and every tile links to that screen.
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
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };

  const columns: readonly Column<(typeof top)[number]>[] = [
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

  return (
    <>
      {/* Tier one. What the estate costs and what is open, at a glance. */}
      <section data-testid="home-summary" aria-label="Summary">
        <div data-testid="home-tile" aria-label="Effective Cost">
          <h3>
            <Link to="/analyze/explorer">Effective Cost, this period</Link>
          </h3>
          <StateBoundary state={spendState} coverageShownElsewhere>
            <p data-testid="home-spend">
              <Figure
                value={{
                  kind: 'measured',
                  amount: Number(summary?.current.effective_cost ?? 0),
                }}
                freshness={{
                  asOf: new Date(spendEnvelope?.meta.as_of ?? 0),
                  collectedAt: new Date(spendEnvelope?.meta.collected_at ?? 0),
                }}
              />
            </p>
            {/* Null is not zero. A period with nothing to compare against has no
                change, and rendering that as a flat zero would claim the estate held
                steady when nobody has looked. */}
            {summary?.change === null || summary?.change === undefined ? (
              <p data-testid="home-spend-note">
                no earlier period collected to compare against
              </p>
            ) : (
              <p data-testid="home-spend-change">
                <Figure
                  value={{ kind: 'measured', amount: Number(summary.change) }}
                  freshness={{
                    asOf: new Date(spendEnvelope?.meta.as_of ?? 0),
                    collectedAt: new Date(spendEnvelope?.meta.collected_at ?? 0),
                  }}
                />{' '}
                against {summary.previous?.period ?? 'the period before'}
              </p>
            )}
            {/* The shape, which is the thing a table of twenty six rows cannot show. The
                seeded estate's last day is half as expensive again as the one before it,
                and that is invisible in a figure and unmissable in a picture. */}
            <BarChart
              points={days.map((day) => ({
                label: day.day.slice(5),
                value: Number(day.effective_cost),
              }))}
              provenance="measured"
              label={
                days.length > 1
                  ? `Daily effective cost across ${String(days.length)} days, ` +
                    `from ${days[0]?.day ?? ''} to ${days[days.length - 1]?.day ?? ''}`
                  : 'Daily effective cost, not enough days collected to show a shape'
              }
              format={(value) =>
                `$${value.toLocaleString('en-GB', { maximumFractionDigits: 0 })}`
              }
            />
          </StateBoundary>
        </div>

        <div data-testid="home-tile" aria-label="Budget">
          <h3>
            <Link to="/plan/budgets">Budget, this period</Link>
          </h3>
          <StateBoundary state={budgetState} coverageShownElsewhere>
            {worstBudget === null ? null : (
              <>
                <p data-testid="home-tile-note">{worstBudget.name}</p>
                {/* The tile shows the budget running furthest ahead of its calendar rather
                    than a total, because budgets do not add up: four healthy ones and one
                    blown one average to fine and the blown one is the news. */}
                <p data-testid="home-budget-figure">
                  {Number(worstBudget.actual ?? 0).toLocaleString('en-GB', {
                    style: 'currency',
                    currency: worstBudget.currency,
                    currencyDisplay: 'narrowSymbol',
                    maximumFractionDigits: 0,
                  })}
                </p>
                <BudgetBar budget={worstBudget} />
                {/* The count of the others, so one card never reads as the whole position. */}
                <p data-testid="home-budget-count">
                  {budgetRows.length === 1
                    ? 'the only budget collected'
                    : `worst of ${String(budgetRows.length)} budgets`}
                  {budgetEnvelope?.data.unsupported
                    ? `, ${String(budgetEnvelope.data.unsupported)} with no number`
                    : ''}
                </p>
              </>
            )}
          </StateBoundary>
        </div>

        <div data-testid="home-tile" aria-label="Open findings">
          <h3>
            <Link to="/govern/query-cost">Open findings</Link>
          </h3>
          <StateBoundary state={findingsState} coverageShownElsewhere>
            <p data-testid="home-count">{rows.length}</p>
            {/* The badge carries the word as well as the fill, so the level is
                never colour alone. */}
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
                {/* Modelled, not measured. A group sums findings whose
                    provenance differs, and calling a mixed total measured would
                    claim more than the weakest figure in it supports. */}
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
            {/* Always a ratio. A surface Meter could not read is not a surface
                with nothing in it, so the readable count never stands alone. */}
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

        {/* Architectural constraint 7: the platform's own cost is on the front
            page. It is Home only, because it is not a property of the accounts
            screen. Last of the four because it is the one figure here that is
            about Meter rather than about the estate Meter is watching. */}
        <div data-testid="home-tile" aria-label="Meter cost">
          <h3>
            <Link to="/platform/cost">Meter cost, this month</Link>
          </h3>
          <StateBoundary state={costState} coverageShownElsewhere>
            {grand ? (
              <Figure
                value={{ kind: 'measured', amount: grand.total }}
                freshness={{
                  asOf: new Date(grand.asOf),
                  collectedAt: new Date(grand.collectedAt),
                }}
                label="Meter cost"
              />
            ) : null}
          </StateBoundary>
        </div>
      </section>

      {/* Tier two. What to do about it. Two panels since 2026-09-26, and the order is the
          claim: Top actions answers what should I do this morning across the whole estate,
          and the findings table below it is the same question narrowed to query governance.
          A reader who acts on the first one is acting on the larger number. */}
      <section data-testid="home-actions" aria-label="Top actions">
        <StateBoundary state={actionsState}>
          <TopActions recommendations={actionRows} freshness={freshness} />
        </StateBoundary>
      </section>

      <section data-testid="home-attention" aria-label="Top findings by dollar">
        <h3>
          <Link to="/govern/query-cost">Top findings by dollar</Link>
        </h3>
        <StateBoundary state={findingsState}>
          <DataTable
            rows={top}
            columns={columns}
            rowKey={(row) => row.finding_id}
            caption={`The ${String(top.length)} most expensive, of ${String(rows.length)}`}
          />
        </StateBoundary>
      </section>

      {/* Tier three. What has not been built, still named, no longer shouting. */}
      <ArrivingRail slots={ABSENT} />
    </>
  );
}
