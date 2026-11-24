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
  const span = high - low || 1;
  const step = width / (points.length - 1);
  const path = points
    .map((value, index) => {
      const x = index * step;
      const y = height - ((value - low) / span) * height;
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
