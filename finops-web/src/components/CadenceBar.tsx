/**
 * How late a collector is against its own cadence. FEAT-006.
 *
 * **A third scaling rule, and it exists because neither of the other two fits.** `RankedBars`
 * draws a share of a total, and collectors do not add up. `PercentCell` draws a fraction of a
 * known maximum, and there is no maximum here: a collector an hour past a one hour cadence is at
 * one, and one that has not run for a fortnight is at three hundred and thirty six. So the track
 * runs from nothing to twice the cadence and the due point sits in the middle of it, which makes
 * the only question a reader has, is this late, answerable by which side of the tick the fill
 * ends on.
 *
 * **One threshold per collector, never one for the estate.** A collector on a five minute cadence
 * and one on a daily cadence are both healthy at an hour old and both alarming at a week. A single
 * staleness threshold would call the first fine and the second broken at exactly the same moment,
 * which is the mistake this screen was built to avoid, so the denominator is the collector's own
 * cadence every time.
 *
 * **Past twice its cadence the bar stops and says so.** A collector at nine times its cadence and
 * one at two and a half would otherwise draw identically, so the bar is marked as running off the
 * scale and the multiple is written beside it. Clamping without the mark is how a chart quietly
 * flattens its worst rows into its merely bad ones.
 *
 * **Two absences, and they are not the same absence.** A collector that has never succeeded has no
 * age, and a collector nothing schedules has no cadence, so its lateness is undefined rather than
 * nought. Both render words and no bar: an empty track reads as a measurement that came back zero,
 * and for freshness that says collected this instant, which is the opposite of the truth.
 */

import { latenessOf } from './lateness';

/** Where the due point sits on the track. Half, so the track runs to twice the cadence. */
const DUE_AT = 0.5;

export interface CadenceBarProps {
  /** Seconds since this collector last succeeded, or null where it never has. */
  readonly ageSeconds: number | null;
  /** Its interval from `collector_schedule`, or null where nothing schedules it. */
  readonly cadenceSeconds: number | null;
}

function multipleOf(lateness: number): string {
  // Two places under one, because the difference between 0.05 and 0.4 of a cadence is the
  // difference between just collected and nearly due, and one place renders both as 0.0.
  return lateness < 1 ? `${lateness.toFixed(2)}x` : `${lateness.toFixed(1)}x`;
}

export function CadenceBar({ ageSeconds, cadenceSeconds }: CadenceBarProps) {
  const lateness = latenessOf(ageSeconds, cadenceSeconds);
  if (lateness === null) {
    return (
      <span data-testid="cadence-absent" data-state="never-collected">
        {ageSeconds === null
          ? 'never collected, so there is no age'
          : 'nothing schedules this, so it cannot be late'}
      </span>
    );
  }

  const clamped = lateness > 2;
  const fill = Math.min(lateness * DUE_AT, 1);
  const state = lateness > 1 ? 'over' : 'due';
  return (
    <span data-testid="cadence" data-state={state} data-clamped={clamped}>
      <span data-testid="cadence-multiple">{multipleOf(lateness)}</span>
      {/* Decoration. The multiple beside it is the content, so this is hidden rather than
          duplicating a number that is already read out. */}
      <span data-testid="cadence-track" aria-hidden="true">
        <i style={{ width: `${String(fill * 100)}%` }} />
        {/* Due. Everything to its right is late, which is the only reading this needs. */}
        <b style={{ left: `${String(DUE_AT * 100)}%` }} />
      </span>
    </span>
  );
}
