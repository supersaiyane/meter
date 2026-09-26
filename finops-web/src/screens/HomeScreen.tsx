import { useMemo } from 'react';
import { Link } from 'react-router';

import {
  usePlatformCost,
  useQueryFindings,
  useQueryGroups,
  useQuerySurfaces,
} from '../api/queries';
import { grandTotal, rollUp } from './platformRollUp';
import { Figure } from '../components/Figure';
import { DataTable } from '../components/DataTable';
import { SeverityBadge, type Severity } from '../components/SeverityBadge';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { severityOf } from './querySeverity';
import { surfaceStateFor } from './surfaceStateFor';
import type { ApiQueryFinding, ApiQueryGroup, ApiSurfaceInstance } from '../api/types';

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
  const costState = surfaceStateFor(
    cost,
    cost.data?.meta,
    costRows.length,
    'none',
    'platform_cost',
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
        <div data-testid="home-tile" aria-label="Open findings">
          <h3>
            <Link to="/governance/queries">Open findings</Link>
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
            <Link to="/governance/queries">Largest cause</Link>
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
                <p data-testid="home-tile-note">
                  {worst.findings} findings, one fault
                </p>
              </>
            ) : null}
          </StateBoundary>
        </div>

        <div data-testid="home-tile" aria-label="Surfaces under audit">
          <h3>
            <Link to="/governance/instances">Surfaces under audit</Link>
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
