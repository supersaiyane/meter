import { useMemo, useState } from 'react';

import { usePlatformCost } from '../api/queries';
import { KpiTile } from '../components/charts';
import { Link } from '../shell/links';
import { useReportMeta } from '../shell/metaRegistry';
import { dollars } from './exploreModel';
import { OverviewEngineering } from './OverviewEngineering';
import { OverviewExecutive } from './OverviewExecutive';
import { OverviewFinOps } from './OverviewFinOps';
import { PERSONAS, choosePersona, storedPersona, type Persona } from './personas';
import { grandTotal, rollUp } from './platformRollUp';
import { surfaceStateFor } from './surfaceStateFor';

/**
 * The front page: three dashboards, one per persona, FEAT-070 and P8 spec section 5.8. The
 * FinOps practitioner's is the one drawn on 2026-10-05 and the one a reader opens on until they
 * choose another, and their last choice is remembered.
 *
 * Three rules carry it, unchanged from the single page it replaced.
 *
 * It owns no data of its own. Every figure is read through the hook of a screen that exists
 * elsewhere, Cost Explorer's views written as the Explorer writes them, and every figure links to
 * that screen. A home screen with its own query will one day disagree with the screen it
 * summarises, and a reader who catches that disagreement stops trusting both.
 *
 * An unfilled slot names what will fill it. It never renders as zero, blank, or a broken panel,
 * and a figure the data cannot support says why.
 *
 * Meter's own cost is on it whichever dashboard is open, architectural constraint 7.
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
 * Only the slots that are still empty. A slot leaves this list the day its sub project lands.
 * Empty today, and the rail draws nothing while it is, rather than a heading over nothing.
 * Spend, trend, realized savings and top movers each stood here once and left the day what they
 * promised was built; top movers is a figure on the Executive dashboard since FEAT-070.
 */
const ABSENT: readonly SlotDef[] = [];

/**
 * The absences, as one rail rather than a stack of panels. Each entry keeps its own test id, its
 * own wording and its own link. Nothing at all when there is nothing still to arrive.
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
 * Architectural constraint 7: the platform's own cost is on the front page. It is the one figure
 * here about Meter rather than about the estate Meter is watching.
 */
function MeterCostTile() {
  const cost = usePlatformCost();
  useReportMeta('platform-cost', cost.data?.meta);
  const rows = useMemo(() => rollUp(cost.data?.data ?? []), [cost.data]);
  const grand = useMemo(() => grandTotal(rows), [rows]);
  const state = surfaceStateFor(cost, cost.data?.meta, rows.length, 'none', 'platform_cost');
  return (
    <KpiTile
      label="Meter cost, this month"
      href="/platform/cost"
      provenance="measured"
      format={dollars}
      value={grand?.total ?? null}
      previous={null}
      period="last month"
      points={[]}
      state={state}
      formula="The platform's own resources, tagged finops:module, summed across its modules"
    />
  );
}

/** Three radios rather than tabs that hide their state, as the theme control is. */
function PersonaSwitch({
  persona,
  onChoose,
}: {
  readonly persona: Persona;
  readonly onChoose: (persona: Persona) => void;
}) {
  return (
    <fieldset data-testid="persona">
      <legend>Dashboard</legend>
      {PERSONAS.map((one) => (
        <label key={one.id}>
          <input
            type="radio"
            name="meter-persona"
            value={one.id}
            checked={persona === one.id}
            onChange={() => {
              onChoose(one.id);
            }}
          />
          {one.label}
        </label>
      ))}
    </fieldset>
  );
}

export function HomeScreen() {
  const [persona, setPersona] = useState<Persona>(storedPersona);
  const meterCost = <MeterCostTile />;
  const choose = (next: Persona) => {
    choosePersona(next);
    setPersona(next);
  };
  return (
    <>
      <PersonaSwitch persona={persona} onChoose={choose} />
      {persona === 'executive' ? <OverviewExecutive meterCost={meterCost} /> : null}
      {persona === 'engineering' ? <OverviewEngineering meterCost={meterCost} /> : null}
      {persona === 'finops' ? <OverviewFinOps meterCost={meterCost} /> : null}
      <ArrivingRail slots={ABSENT} />
    </>
  );
}
