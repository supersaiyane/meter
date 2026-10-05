import type { Provenance } from '../provenance';
import { Sparkline } from '../Sparkline';
import { ChartTable } from './ChartTable';

/**
 * One figure, the change since the period before, and its recent shape. P8 spec section 5.4.
 *
 * The change is stated in words with its sign and the period it is measured against, and is
 * not coloured good or bad: whether a cost going up is bad depends on what bought it, and a
 * red arrow decides that for the reader. A figure that was not collected says so and has no
 * change, because a missing figure drawn as zero is the failure this product exists to stop.
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
}

export function KpiTile({
  label,
  value,
  previous,
  points,
  provenance,
  format,
  period,
}: KpiTileProps) {
  const change = value !== null && previous !== null ? value - previous : null;
  const ratio =
    change !== null && previous !== null && previous !== 0 ? change / previous : null;
  const said = (figure: number | null, absent: string): string =>
    figure === null ? absent : format(figure);

  return (
    <section
      className="meter-kpi meter-panel"
      aria-label={label}
      data-testid="kpi-tile"
      data-provenance={provenance}
    >
      <h3>{label}</h3>
      <p data-testid="kpi-value" className="meter-numeral">
        {said(value, 'Not yet collected')}
      </p>
      {ratio === null ? null : (
        <p data-testid="kpi-delta">
          {`${ratio >= 0 ? '+' : ''}${(ratio * 100).toFixed(1)}% against ${period}`}
        </p>
      )}
      <Sparkline points={points} provenance={provenance} label={`${label}, trend`} />
      <ChartTable
        caption={label}
        rowHeader="Figure"
        columns={['Value']}
        rows={[
          { label: 'This period', cells: [{ value, text: said(value, 'Not yet collected') }] },
          {
            label: `Previous, ${period}`,
            cells: [{ value: previous, text: said(previous, 'Not yet collected') }],
          },
          { label: 'Change', cells: [{ value: change, text: said(change, 'Not available') }] },
        ]}
      />
    </section>
  );
}
