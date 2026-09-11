import { useMemo } from 'react';
import { Link } from 'react-router';

import { usePlatformCost, useQueryFindings } from '../api/queries';
import { grandTotal, rollUp } from './platformRollUp';
import { Figure } from '../components/Figure';
import { DataTable } from '../components/DataTable';
import { SeverityBadge } from '../components/SeverityBadge';
import { StateBoundary } from '../components/StateBoundary';
import type { Column } from '../components/tableConfig';
import { useReportMeta } from '../shell/metaRegistry';
import { severityOf } from './querySeverity';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * The front page. A trust strip above the money, per
 * `docs/13-UI-ARCHITECTURE.md` section 6.
 *
 * Two rules carry this screen.
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
 */

interface SlotDef {
  readonly id: string;
  readonly label: string;
  /** The screen that will own this figure. */
  readonly owns: string;
  /** Null when built. The sub project name when it is not. */
  readonly arrives: string | null;
}

const SLOTS: readonly SlotDef[] = [
  {
    id: 'spend',
    label: 'Total spend, month to date',
    owns: '/cost',
    arrives: 'P1 Cost Intelligence',
  },
  { id: 'trend', label: 'Trend, 30 days', owns: '/cost', arrives: 'P1 Cost Intelligence' },
  { id: 'movers', label: 'Top movers', owns: '/cost', arrives: 'P1 Cost Intelligence' },
  {
    id: 'findings',
    label: 'Top findings by dollar',
    owns: '/governance/queries',
    // Built. TASK-P2-021 gave this slot a route, so the front page shows the
    // finding rather than the name of the sub project that would one day
    // provide it. That is what makes this page the progress view.
    arrives: null,
  },
  {
    id: 'savings',
    label: 'Realized savings, trailing 60 days',
    owns: '/waste/savings',
    arrives: 'P3 Utilization and Rightsizing',
  },
];

function EmptySlot({ slot }: { readonly slot: SlotDef }) {
  return (
    <section data-testid={`home-slot-${slot.id}`} aria-label={slot.label}>
      <h3>{slot.label}</h3>
      <p data-state="never-collected">
        not yet collected, arrives with <Link to={slot.owns}>{slot.arrives}</Link>
      </p>
    </section>
  );
}

/**
 * The three most expensive findings, read through the findings screen's own
 * hook and its own query key, so the two can never disagree. Home owns no data.
 */
function FindingsSlot({ slot }: { readonly slot: SlotDef }) {
  const query = useQueryFindings();
  const envelope = query.data?.data;
  const rows = envelope?.data ?? [];
  const top = rows.slice(0, TOP_FINDINGS);
  useReportMeta('home-query-findings', envelope?.meta);
  const state = surfaceStateFor(query, envelope?.meta, rows.length, 'none', 'query_audit');

  const freshness = {
    asOf: new Date(envelope?.meta.as_of ?? 0),
    collectedAt: new Date(envelope?.meta.collected_at ?? 0),
  };
  const columns: readonly Column<(typeof top)[number]>[] = [
    { key: 'severity', header: 'Severity', render: (row) => <SeverityBadge level={severityOf(row)} /> },
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
    <section data-testid={`home-slot-${slot.id}`} aria-label={slot.label}>
      <h3>
        <Link to={slot.owns}>{slot.label}</Link>
      </h3>
      <StateBoundary state={state}>
        <DataTable
          rows={top}
          columns={columns}
          rowKey={(row) => row.finding_id}
          caption={`The ${String(top.length)} most expensive, of ${String(rows.length)}`}
        />
      </StateBoundary>
    </section>
  );
}

/** Three. A front page summary that needs scrolling is a second screen. */
const TOP_FINDINGS = 3;

export function HomeScreen() {
  const query = usePlatformCost();
  useReportMeta('platform-cost', query.data?.meta);
  const rows = useMemo(() => rollUp(query.data?.data ?? []), [query.data]);
  const grand = useMemo(() => grandTotal(rows), [rows]);
  const state = surfaceStateFor(query, query.data?.meta, rows.length, 'none', 'platform_cost');

  return (
    <>
      {/* Architectural constraint 7: the platform's own cost is on the front
          page. It is Home only, because it is not a property of the accounts
          screen. */}
      <section aria-label="Meter cost">
        <h3>
          <Link to="/platform/cost">Meter cost, this month</Link>
        </h3>
        <StateBoundary state={state}>
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
      </section>

      {SLOTS.map((slot) =>
        slot.arrives === null ? (
          <FindingsSlot key={slot.id} slot={slot} />
        ) : (
          <EmptySlot key={slot.id} slot={slot} />
        ),
      )}
    </>
  );
}
