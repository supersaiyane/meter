import type { ReactNode } from 'react';

import { Link } from '../../shell/links';
import type { Provenance } from '../provenance';
import { Sparkline } from '../Sparkline';
import { StateBoundary } from '../StateBoundary';
import type { SurfaceState, SurfaceStateKind } from '../surfaceState';
import { ChartTable } from './ChartTable';

/**
 * One figure, the change since the period before, and its recent shape. P8 spec section 5.4.
 *
 * The change is stated in words with its sign and the period it is measured against, and is
 * not coloured good or bad: whether a cost going up is bad depends on what bought it, and a
 * red arrow decides that for the reader. A figure that was not collected says so and has no
 * change, because a missing figure drawn as zero is the failure this product exists to stop.
 *
 * On the Overview, FEAT-070, a tile also names its formula and baseline where it is shown,
 * links to the screen that owns the figure, and says why when the data cannot support it at
 * all, which is a different thing from not having been collected yet.
 */

export interface KpiTileProps {
  readonly label: string;
  readonly value: number | null;
  readonly previous: number | null;
  readonly points: readonly number[];
  readonly provenance: Provenance;
  readonly format: (value: number) => string;
  /** What the change is measured against, said in words: last month, last week. */
  readonly period: string;
  /** The screen that owns the figure. The label links to it. */
  readonly href?: string;
  /** How the figure is worked out, and against what. */
  readonly formula?: string;
  /** A line under the figure: what it covers, or what is left over. */
  readonly note?: string;
  /** Why the data cannot support the figure. When set there is no figure, change or shape. */
  readonly unsupported?: string;
  /** A forecast's interval, shown as its two ends rather than as one number. */
  readonly range?: { readonly low: number; readonly high: number };
  /** Drawn under the figure, a budget bar for one. */
  readonly children?: ReactNode;
  /**
   * The state of the read behind the figure. Loading, a failure, nothing collected and nothing
   * matched take the figure's place and keep the label, so a failed read is never shown as a
   * figure that was simply not collected.
   */
  readonly state?: SurfaceState;
  /**
   * Drawn last, whatever the state: facts and controls that do not depend on the figure, so a
   * failed cost read on a geography's tile still leaves its resource count and the control that
   * lists them. TASK-P8-017.
   */
  readonly footer?: ReactNode;
}

/** The states that stand in for a figure rather than sit beside one. */
const REPLACING: ReadonlySet<SurfaceStateKind> = new Set([
  'loading',
  'empty',
  'never-collected',
  'failed',
]);

const PROVENANCE_WORDS: Readonly<Record<Provenance, string>> = {
  measured: 'Measured',
  modelled: 'Modelled',
  forecast: 'Forecast',
};

export function KpiTile({
  label,
  value,
  previous,
  points,
  provenance,
  format,
  period,
  href,
  formula,
  note,
  unsupported,
  range,
  children,
  state,
  footer,
}: KpiTileProps) {
  const change = value !== null && previous !== null ? value - previous : null;
  const ratio =
    change !== null && previous !== null && previous !== 0 ? change / previous : null;
  const said = (figure: number | null, absent: string): string =>
    figure === null ? absent : format(figure);
  const shown =
    range === undefined
      ? said(value, 'Not yet collected')
      : `${format(range.low)} to ${format(range.high)}`;

  return (
    <section
      className="meter-kpi meter-panel"
      aria-label={label}
      data-testid="kpi-tile"
      data-provenance={provenance}
    >
      <h3>
        {href === undefined ? label : <Link to={href}>{label}</Link>}{' '}
        <span data-testid="kpi-provenance">{PROVENANCE_WORDS[provenance]}</span>
      </h3>
      {state !== undefined && REPLACING.has(state.kind) ? (
        <StateBoundary state={state} coverageShownElsewhere>
          {null}
        </StateBoundary>
      ) : unsupported === undefined ? (
        <>
          <p data-testid="kpi-value" className="meter-numeral">
            {shown}
          </p>
          {ratio === null ? null : (
            <p data-testid="kpi-delta">
              {`${ratio >= 0 ? '+' : ''}${(ratio * 100).toFixed(1)}% against ${period}`}
            </p>
          )}
          {note === undefined ? null : <p data-testid="kpi-note">{note}</p>}
          {children}
          <Sparkline points={points} provenance={provenance} label={`${label}, trend`} />
          <ChartTable
            caption={label}
            rowHeader="Figure"
            columns={['Value']}
            rows={
              range === undefined
                ? [
                    {
                      label: 'This period',
                      cells: [{ value, text: said(value, 'Not yet collected') }],
                    },
                    {
                      label: `Previous, ${period}`,
                      cells: [{ value: previous, text: said(previous, 'Not yet collected') }],
                    },
                    {
                      label: 'Change',
                      cells: [{ value: change, text: said(change, 'Not available') }],
                    },
                  ]
                : [
                    { label: 'Low', cells: [{ value: range.low, text: format(range.low) }] },
                    { label: 'High', cells: [{ value: range.high, text: format(range.high) }] },
                  ]
            }
          />
        </>
      ) : (
        <p data-testid="kpi-unsupported">{unsupported}</p>
      )}
      {formula === undefined ? null : <p data-testid="kpi-formula">{formula}</p>}
      {footer}
    </section>
  );
}
