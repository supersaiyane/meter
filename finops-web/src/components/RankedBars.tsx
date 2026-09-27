import type { ReactNode } from 'react';

import type { Provenance } from './provenance';
import { rankedRows } from './rankedRows';

/**
 * A ranked breakdown, drawn. The second chart in the product.
 *
 * **Horizontal, and CSS rather than SVG.** `BarChart` is vertical because its axis is time and
 * time has short labels. This one's axis is categories, and a category is a word: `AmazonEC2`,
 * `EBS_UNATTACHED`, `nobody tagged this`. Vertical bars would need rotated labels, which nobody
 * reads, or truncation, which hides the thing the row is about. Laying it out in CSS also means
 * the labels are real text that wraps, selects and is read by a screen reader in order, where SVG
 * text would need its width measured to avoid overlapping.
 *
 * **Bars are a share of the total, not of the largest.** Scaling to the largest makes the top row
 * fill the track always, so a breakdown where one service is 90 percent of spend looks identical
 * to one where the top three are evenly matched. Share of the total is the fact somebody wants:
 * the top bar filling a third of its track says a third of the money is there, and the eye adds
 * the first few rows up on its own.
 *
 * **The bars are decoration and the numbers are the content.** Every row states its label and its
 * value as text, and the bars carry `aria-hidden`, because a reader who cannot see them loses
 * nothing: they are a faster way to compare numbers that are already written down. This is the
 * opposite choice from `BarChart`, where twenty six bars would be twenty six unreadable rows and
 * the drawing therefore carries a summary label instead.
 */

/**
 * What the bar lengths are relative to.
 *
 * `total` is the default and the honest one for a breakdown of a whole: a bar filling a third of
 * its track means a third of the money. `largest` is for a set of figures that must not be added
 * up, where the only comparison available is with each other, and it suppresses the share column
 * because a percentage with no whole behind it is a number nobody can check.
 */
export type RankedBasis = 'total' | 'largest';

export interface RankedPoint {
  readonly label: string;
  readonly value: number;
  /** Rendered instead of the formatted value where a caller has something better to say. */
  readonly note?: ReactNode;
  /**
   * A reference value on the same scale as `value`, drawn as a tick in the track.
   *
   * The anomalies screen is what this is for: the bar is what a day actually cost and the tick
   * is what that day usually costs, so how far past the tick the bar runs is the finding. Kept
   * on the same divisor as the bar, because a tick scaled any other way would be a mark in a
   * position that means nothing.
   */
  readonly marker?: number;
  /**
   * A row that is not one of the things being ranked. Unallocated spend is the case this exists
   * for: it is a real measured number that belongs to nobody, so it must be in the picture and
   * must not look like an owner. Drawn as an outline rather than a solid, and deliberately not
   * as a hatch, because the hatch already means modelled and one mark with two meanings is a
   * mark a reader cannot read.
   */
  readonly isGap?: boolean;
}

export interface RankedBarsProps {
  readonly points: readonly RankedPoint[];
  /**
   * Measured or modelled, and deliberately required. A default would be a default that quietly
   * promotes a modelled saving to a measured one, which is the single claim this product cannot
   * be wrong about. The hatch is the same one `BarChart` uses, so a reader learns it once.
   */
  readonly provenance: Provenance;
  readonly format: (value: number) => string;
  /**
   * How many rows to draw before collapsing the rest into one. Forty categories at two percent
   * each are forty stubs, which is a picture of nothing. The remainder is never dropped: it is
   * summed into a final row that says how many rows it stands for, because a chart that silently
   * shows the top eight of forty is a chart that lies by omission.
   */
  readonly limit?: number;
  /** What the rest row is called. Named by the caller because "other" means different things. */
  readonly restLabel?: string;
  /** Defaults to `total`. See `RankedBasis`. */
  readonly basis?: RankedBasis;
}

export function RankedBars({
  points,
  provenance,
  format,
  limit = 8,
  restLabel = 'everything else',
  basis = 'total',
}: RankedBarsProps) {
  const rows = rankedRows(points, limit, restLabel, basis);
  if (rows.length === 0) {
    return null;
  }
  // On the largest basis nothing is summed, so what is past the limit is stated rather than
  // folded into a row. Saying the count is what keeps a truncated chart from being a chart that
  // lies by omission, which is the same rule the collapsed remainder follows on the other basis.
  const undrawn = basis === 'largest' ? points.length - rows.length : 0;
  return (
    <ol data-testid="ranked-bars" data-provenance={provenance}>
      {rows.map((row) => (
        <li key={row.label} data-testid="ranked-row" data-gap={row.isGap === true}>
          <span data-testid="ranked-label">{row.label}</span>
          {/* Decoration over content. The number is written to its right either way. */}
          <span data-testid="ranked-track" aria-hidden="true">
            <i style={{ width: `${String(row.share * 100)}%` }} />
            {row.markerShare === undefined ? null : (
              <b style={{ left: `${String(Math.min(row.markerShare, 1) * 100)}%` }} />
            )}
          </span>
          <span data-testid="ranked-value">{row.note ?? format(row.value)}</span>
          {/* Omitted where the values are not parts of a whole. A percentage printed there
              would be a share of a total this product refuses to compute. */}
          {basis === 'total' ? (
            <span data-testid="ranked-share">{(row.share * 100).toFixed(1)}%</span>
          ) : null}
        </li>
      ))}
      {undrawn > 0 ? (
        <li data-testid="ranked-undrawn">
          <span>
            {undrawn === 1 ? '1 more is not drawn' : `${String(undrawn)} more are not drawn`},
            because they are not parts of a whole and cannot be added into one row
          </span>
        </li>
      ) : null}
    </ol>
  );
}
