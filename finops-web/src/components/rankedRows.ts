import type { RankedBasis, RankedPoint } from './RankedBars';

/**
 * The rows a ranked breakdown draws, largest first, with anything past the limit summed into one.
 *
 * Its own module rather than a second export from the component, because this is the part with
 * its own test and a file that exports both cannot be hot reloaded. The arithmetic is here for a
 * reason: a ranked chart fails quietly. A total computed after the remainder was collapsed rather
 * than before it makes every share too large and every bar too long, and the picture still looks
 * plausible, because the rows are in the right order and the biggest is still biggest.
 */

interface Row extends RankedPoint {
  readonly share: number;
  /** The reference, on the same divisor as `share`, or undefined where the row has none. */
  readonly markerShare?: number;
}

/**
 * One row, with its bar and its reference both divided by the same number.
 *
 * One helper rather than the arithmetic twice, because a marker scaled by the total on one
 * basis and by the peak on the other would be a tick whose position quietly meant a different
 * thing per chart, and no rendering assertion would show it.
 */
function withMarker(point: RankedPoint, divisor: number): Row {
  const share = divisor > 0 ? point.value / divisor : 0;
  if (point.marker === undefined) {
    return { ...point, share };
  }
  return { ...point, share, markerShare: divisor > 0 ? point.marker / divisor : 0 };
}

export function rankedRows(
  points: readonly RankedPoint[],
  limit: number,
  restLabel: string,
  basis: RankedBasis = 'total',
): readonly Row[] {
  const ordered = [...points].sort((left, right) => right.value - left.value);

  // Where the values must not be added up, the bar is scaled to the largest of them and no
  // share is computed at all. The realized savings screen is the case: its totals are grouped
  // by verdict and never summed, because one verdict's realized figure and another's are not
  // parts of a whole, so a percentage here would be a share of a number the product refuses
  // to state. Nothing is collapsed either, since collapsing a remainder is that same sum.
  if (basis === 'largest') {
    const peak = ordered.reduce((most, point) => Math.max(most, point.value), 0);
    // Truncated rather than collapsed. Summing a remainder into one row is the addition this
    // basis exists to avoid, so the rows past the limit are simply not drawn and the component
    // says how many. Thirty anomalies of nearly equal size is a wall of identical bars that
    // answers nothing, which is what the anomalies screen looked like before this.
    return ordered.slice(0, limit).map((point) => withMarker(point, peak));
  }

  // The total is over everything, before any collapse, so a share is a share of the estate and
  // not of the part that happened to fit.
  const total = points.reduce((sum, point) => sum + point.value, 0);
  const shareOf = (value: number) => (total > 0 ? value / total : 0);
  if (ordered.length <= limit) {
    return ordered.map((point) => withMarker(point, total));
  }
  const shown = ordered.slice(0, limit);
  const rest = ordered.slice(limit);
  const restValue = rest.reduce((sum, point) => sum + point.value, 0);
  return [
    ...shown.map((point) => ({ ...point, share: shareOf(point.value) })),
    {
      label: `${restLabel}, ${String(rest.length)} more`,
      value: restValue,
      share: shareOf(restValue),
      isGap: true,
    },
  ];
}
