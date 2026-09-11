import { useMemo } from 'react';
import { Link } from 'react-router';

import { usePlatformCost } from '../api/queries';
import { grandTotal, rollUp } from './platformRollUp';
import { Figure } from '../components/Figure';
import { StateBoundary } from '../components/StateBoundary';
import { useReportMeta } from '../shell/metaRegistry';
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
    arrives: 'P2 Query Cost Governance',
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
              freshness={{ asOf: new Date(grand.asOf), collectedAt: new Date(grand.collectedAt) }}
              label="Meter cost"
            />
          ) : null}
        </StateBoundary>
      </section>

      {SLOTS.map((slot) => (slot.arrives === null ? null : <EmptySlot key={slot.id} slot={slot} />))}
    </>
  );
}
