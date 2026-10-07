import { ChartTable } from './charts/ChartTable';
import type { Provenance } from './provenance';

/**
 * A column of days, drawn so the shape is the point and the values are still readable.
 *
 * Hand rolled SVG, like `Sparkline`, for the same two reasons. A charting library is a
 * dependency that has to go through `make dep-check` to draw twenty six rectangles. And every
 * one of them wants to animate a bar up from zero on mount, which is a number lying for four
 * hundred milliseconds in a product whose whole claim is that its numbers are trustworthy.
 *
 * **Not a sparkline.** A sparkline answers "is this going up" and refuses to be read off.
 * This is the opposite: it has a scale, its tallest bar is labelled, and the reader is meant
 * to point at a day. The two exist side by side because they answer different questions and a
 * chart that tries to do both ends up with the axes removed and an invitation to read values
 * anyway.
 *
 * **Provenance survives.** A modelled series is hatched, exactly as a modelled figure is,
 * because a shape built from projections must not be mistaken for one built from measurements.
 *
 * **It is one image to a screen reader, with the summary in its label.** Twenty six bars
 * announced one at a time is twenty six announcements nobody listens to; the label carries the
 * range, the peak and the direction, which is what the picture actually says.
 */

export interface BarChartPoint {
  readonly label: string;
  readonly value: number;
}

export interface BarChartProps {
  readonly points: readonly BarChartPoint[];
  readonly provenance: Provenance;
  /** What the picture says, for a reader who cannot see it. */
  readonly label: string;
  /** Formats a value for the peak marker and the axis. */
  readonly format: (value: number) => string;
  readonly height?: number;
}

export function BarChart({ points, provenance, label, format, height = 120 }: BarChartProps) {
  if (points.length < 2) {
    // One bar is not a shape. Drawing it would assert a trend nobody has watched, which is
    // the same refusal Sparkline makes and for the same reason.
    return (
      <p data-testid="chart-absent" data-state="never-collected">
        {points.length === 1
          ? 'Seen once. There is no shape until it has been collected twice.'
          : 'Nothing collected yet.'}
      </p>
    );
  }

  const values = points.map((one) => one.value);
  const peak = Math.max(...values);
  // From zero, always. A bar chart with a non zero baseline exaggerates every difference on
  // it, and the one thing a cost chart must not do is make a normal week look like a crisis.
  const floor = 0;
  const span = peak - floor || 1;

  return (
    <figure data-testid="bar-chart" data-provenance={provenance}>
      <svg
        viewBox={`0 0 ${String(points.length * 10)} ${String(height)}`}
        preserveAspectRatio="none"
        height={height}
        width="100%"
        role="img"
        aria-label={label}
      >
        {provenance !== 'measured' ? (
          <defs>
            <pattern
              id="meter-bar-hatch"
              width="4"
              height="4"
              patternUnits="userSpaceOnUse"
              patternTransform="rotate(45)"
            >
              <line x1="0" y1="0" x2="0" y2="4" stroke="currentColor" strokeWidth="1.5" />
            </pattern>
          </defs>
        ) : null}
        {points.map((point, index) => {
          const tall = ((point.value - floor) / span) * (height - 2);
          return (
            <rect
              key={point.label}
              x={index * 10 + 1.5}
              y={height - tall}
              width={7}
              height={Math.max(tall, 1)}
              rx="1.5"
              // The peak is marked, because the eye finds the tallest bar anyway and a reader
              // who has found it should not then have to hunt for its value.
              className={point.value === peak ? 'meter-bar meter-bar-peak' : 'meter-bar'}
              fill={provenance === 'measured' ? undefined : 'url(#meter-bar-hatch)'}
            />
          );
        })}
      </svg>
      <figcaption data-testid="bar-chart-axis">
        <span>{points[0]?.label}</span>
        <span data-testid="bar-chart-peak">peak {format(peak)}</span>
        <span>{points[points.length - 1]?.label}</span>
      </figcaption>
      {/* The bars as numbers, for a reader who cannot see them or wants the value of one. */}
      <ChartTable
        caption={label}
        rowHeader="Period"
        columns={['Value']}
        rows={points.map((point) => ({
          label: point.label,
          cells: [{ value: point.value, text: format(point.value) }],
        }))}
      />
    </figure>
  );
}
