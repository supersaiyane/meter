import type { Provenance } from './provenance';

/**
 * A thirty day shape, with no axes and no tooltip.
 *
 * It answers "is this going up" and nothing else. A sparkline that invites you
 * to read a value off it is a chart with the axes removed, which is worse than
 * either.
 *
 * Provenance still applies: a modelled series is drawn dashed, so a shape built
 * from projections is not mistaken for one built from measurements.
 */
export interface SparklineProps {
  readonly points: readonly number[];
  readonly provenance: Provenance;
  readonly label: string;
  readonly width?: number;
  readonly height?: number;
}

export function Sparkline({
  points,
  provenance,
  label,
  width = 120,
  height = 24,
}: SparklineProps) {
  if (points.length < 2) {
    // One point is not a trend, and drawing it as a flat line implies stability
    // that has not been observed.
    return <span data-testid="sparkline" data-empty="true" />;
  }
  const low = Math.min(...points);
  const high = Math.max(...points);
  const span = high - low;
  const step = width / (points.length - 1);
  const path = points
    .map((value, index) => {
      const x = index * step;
      // A series that never changes has no low and no high to scale between.
      // Normalising it anyway put every point at the floor, so a module costing
      // the same every day for thirty days drew the same line as one costing
      // nothing. Flat belongs in the middle. ISS-160.
      const y = span === 0 ? height / 2 : height - ((value - low) / span) * height;
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');

  return (
    <svg
      data-testid="sparkline"
      data-provenance={provenance}
      width={width}
      height={height}
      viewBox={`0 0 ${String(width)} ${String(height)}`}
      role="img"
      aria-label={`${label}, ${provenance}, ${String(points.length)} points`}
    >
      <path
        d={path}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeDasharray={provenance === 'measured' ? undefined : '3 2'}
      />
    </svg>
  );
}
