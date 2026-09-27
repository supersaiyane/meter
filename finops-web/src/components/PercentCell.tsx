import type { Provenance } from './provenance';

/**
 * A percentage in a table cell, with a bar under it. FEAT-019's two percentages.
 *
 * **A fraction of a hundred, not a share of a total, and that is why this is not `RankedBars`.**
 * Coverage and utilization each answer a question about one row: of what could be committed, how
 * much is. Ranking them against each other and drawing shares would produce a number nobody
 * asked for, because two services at eighty percent coverage are both at eighty percent and
 * neither is half of anything.
 *
 * **Deliberately not built on `BudgetBar`.** That drawing is a ten pixel card bar with a pace
 * tick against the calendar; this is a four pixel rule under a figure in a table row. The two
 * share three lines of clamping and no context, and a component that served both would take a
 * size, a marker, a tone and a test id to hide the fact that they are different pictures.
 *
 * **The absence is the component's job.** A null percentage is a commitment that has not started
 * or a service with nothing eligible, and both are real states rather than nought percent. Nought
 * would say the money was wasted. So an absent fraction renders the caller's words and draws no
 * bar at all: an empty track reads as a measurement that came back zero.
 */

export interface PercentCellProps {
  /** Nought to one, or null where the figure does not exist for this row. */
  readonly fraction: number | null;
  /** What to say instead when there is no figure. Never a number, and never blank. */
  readonly absent: string;
  readonly provenance: Provenance;
  /**
   * True where a high figure is the finding rather than the goal. Utilization and coverage are
   * both better high, so nothing here passes it yet, and it exists because the first caller who
   * needs it would otherwise reach for a colour override on a shared class.
   */
  readonly inverted?: boolean;
}

export function PercentCell({ fraction, absent, provenance, inverted }: PercentCellProps) {
  if (fraction === null) {
    return (
      <span data-testid="percent-absent" data-state="never-collected">
        {absent}
      </span>
    );
  }
  const clamped = Math.min(Math.max(fraction, 0), 1);
  return (
    <span data-testid="percent-cell" data-provenance={provenance}>
      <span data-testid="percent-figure">{(fraction * 100).toFixed(1)}%</span>
      {/* Decoration. The figure above is the content, so the bar is hidden from the
          accessibility tree rather than duplicating a number that is already read out. */}
      <span data-testid="percent-track" aria-hidden="true" data-inverted={inverted === true}>
        <i style={{ width: `${String(clamped * 100)}%` }} />
      </span>
    </span>
  );
}
