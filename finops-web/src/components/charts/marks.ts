import { useId } from 'react';

import type { Provenance } from '../provenance';

/** How many series colours the tokens define before they repeat. */
export const SERIES = 6;

/** The share of full colour the faintest heatmap cell keeps, so a zero is still a cell. */
export const HEAT_FLOOR = 0.08;

/**
 * The classes a mark takes: its series colour, and how its provenance draws it. Measured is
 * solid, modelled a lighter fill under the hatch, forecast a dashed outline over a faint fill,
 * the same three marks every chart in the set uses, so a reader learns them once.
 */
export function markClass(provenance: Provenance, series: number): string {
  return `meter-series-${String((series % SERIES) + 1)} meter-mark-${provenance}`;
}

/** An id for a chart's own defs, made safe to stand inside `url(#...)`. */
export function useChartId(): string {
  return `meter-chart-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`;
}

/** Two decimals, enough for a coordinate and short enough to read in a test. */
export function at(value: number): string {
  return value.toFixed(2);
}
