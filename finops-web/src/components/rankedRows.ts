import type { RankedPoint } from './RankedBars';

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
}

export function rankedRows(
  points: readonly RankedPoint[],
  limit: number,
  restLabel: string,
): readonly Row[] {
  // The total is over everything, before any collapse, so a share is a share of the estate and
  // not of the part that happened to fit.
  const total = points.reduce((sum, point) => sum + point.value, 0);
  const shareOf = (value: number) => (total > 0 ? value / total : 0);
  const ordered = [...points].sort((left, right) => right.value - left.value);
  if (ordered.length <= limit) {
    return ordered.map((point) => ({ ...point, share: shareOf(point.value) }));
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
