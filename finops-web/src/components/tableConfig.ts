import type { ReactNode } from 'react';

/**
 * Above this many rows the table windows its output instead of rendering every
 * row into the document.
 *
 * Two hundred is where a dense table stops being something a browser lays out
 * without effort. It is a value rather than a literal inside the component so a
 * test can assert the behaviour changes at the documented point rather than at
 * whatever number happens to be in the code.
 */
export const VIRTUALISE_ABOVE = 200;

/** Estimated row height in pixels, used only to decide what to render. */
export const ROW_HEIGHT = 28;

export interface Column<Row> {
  readonly key: string;
  readonly header: string;
  readonly render: (row: Row) => ReactNode;
  /** Numeric columns are right aligned and tabular. Text columns are not. */
  readonly numeric?: boolean;
}
