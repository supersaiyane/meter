import { useMemo } from 'react';
import { Link } from 'react-router';

import { usePlatformCost, useQueryFindings } from '../api/queries';
import { grandTotal, rollUp } from './platformRollUp';
import { Figure } from '../components/Figure';
import { DataTable } from '../components/DataTable';
import { SeverityBadge, type Severity } from '../components/SeverityBadge';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { severityOf } from './querySeverity';
import { surfaceStateFor } from './surfaceStateFor';
import type { ApiQueryFinding } from '../api/types';

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
 * a summary, then the one thing that needs attention, then the absences. The
 * absences used to be panels drawn at the same weight as the money, which meant
 * nothing on the page outranked anything else. They are one rail now. The claim
 * they make is unchanged, it just no longer outweighs the facts.
 */

interface SlotDef {
  readonly id: string;
  readonly label: string;
  /** The screen that will own this figure. */
  readonly owns: string;
  /** The sub project that will fill it. */
  readonly arrives: string;
}

/**
 * Only the slots that are still empty. A slot leaves this list the day its sub
 * project lands, and becomes a tile above.
 */
const ABSENT: readonly SlotDef[] = [
  {
    id: 'spend',
    label: 'Total spend, month to date',
    owns: '/cost',
    arrives: 'P1 Cost Intelligence',
  },
  { id: 'trend', label: 'Trend, 30 days', owns: '/cost', arrives: 'P1 Cost Intelligence' },
  { id: 'movers', label: 'Top movers', owns: '/cost', arrives: 'P1 Cost Intelligence' },
  {
    id: 'savings',
    label: 'Realized savings, trailing 60 days',
    owns: '/waste/savings',
    arrives: 'P3 Utilization and Rightsizing',
  },
];

/** Three. A front page summary that needs scrolling is a second screen. */
const TOP_FINDINGS = 3;

/** Worst first, which is the order someone reads a severity summary in. */
const SEVERITY_ORDER: readonly Severity[] = [5, 4, 3, 2, 1];

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
 */
function ArrivingRail() {
  return (
    <section data-testid="home-rail" aria-label="Not yet collected">
      <h3>Not yet collected</h3>
      <ul>
        {ABSENT.map((slot) => (
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

export function HomeScreen() {
  const cost = usePlatformCost();
  useReportMeta('platform-cost', cost.data?.meta);
  const costRows = useMemo(() => rollUp(cost.data?.data ?? []), [cost.data]);
  const grand = useMemo(() => grandTotal(costRows), [costRows]);
  const costState = surfaceStateFor(cost, cost.data?.meta, costRows.length, 'none', 'platform_cost');

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
        <Link to={`/governance/queries/${row.finding_id}`}>
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
        {/* Architectural constraint 7: the platform's own cost is on the front
            page. It is Home only, because it is not a property of the accounts
            screen. */}
        <div data-testid="home-tile" aria-label="Meter cost">
          <h3>
            <Link to="/platform/cost">Meter cost, this month</Link>
          </h3>
          <StateBoundary state={costState}>
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

        <div data-testid="home-tile" aria-label="Open findings">
          <h3>
            <Link to="/governance/queries">Open findings</Link>
          </h3>
          <StateBoundary state={findingsState}>
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
      </section>

      {/* Tier two. The one thing worth doing something about. */}
      <section data-testid="home-attention" aria-label="Top findings by dollar">
        <h3>
          <Link to="/governance/queries">Top findings by dollar</Link>
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
      <ArrivingRail />
    </>
  );
}
