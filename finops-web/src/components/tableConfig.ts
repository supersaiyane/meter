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

/**
 * Estimated row height in pixels, used only to decide what to render.
 *
 * It must agree with `--row-height` in `tokens.css`. A virtualiser estimating
 * 28 against rows drawn at 32 scrolls short by an accumulating four pixels a
 * row, which at three hundred rows is a table that will not reach its own end.
 */
export const ROW_HEIGHT = 32;

export interface Column<Row> {
  readonly key: string;
  readonly header: string;
  readonly render: (row: Row) => ReactNode;
  /** Numeric columns are right aligned and tabular. Text columns are not. */
  readonly numeric?: boolean;
  /**
   * A column of prose, which takes the width the others do not need.
   *
   * Without it every column shares the width evenly, and the `why` column, the
   * one that tells a reader what to do about a finding, wrapped into a ribbon
   * about eight characters wide and made every row a hundred pixels tall. A
   * table where the explanation is the narrowest column has its priorities
   * inverted.
   */
  readonly prose?: boolean;
}
