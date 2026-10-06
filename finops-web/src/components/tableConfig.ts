import type { ReactNode } from 'react';

import type { Provenance } from './provenance';

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
  /** What the column sorts by. A column without one does not sort. Null sorts last. */
  readonly sortValue?: (row: Row) => number | string | null;
  /** How the column adds up, where it does. See `columnTotal`. */
  readonly total?: ColumnTotal<Row>;
  /**
   * A test id on each of the column's cells. Kept from the hand drawn tables this one
   * replaced, TASK-P8-013, so moving a table onto it moves nothing a journey reads.
   */
  readonly cellTestId?: string;
  /**
   * The column that names each row, drawn as a row header so a screen reader announces it
   * with every cell in the row. The hand drawn tables had one, and a table without it reads a
   * figure with nothing to say which row it belongs to.
   */
  readonly rowHeader?: boolean;
}

export interface ColumnTotal<Row> {
  /** The figure, or null where this row's figure was not collected. */
  readonly value: (row: Row) => number | null;
  readonly unit: (row: Row) => string;
  readonly provenance: (row: Row) => Provenance;
  /** Draws the sum, through the same component the column's cells use. */
  readonly render: (sum: number, unit: string, provenance: Provenance) => ReactNode;
}

export interface Sort {
  readonly key: string;
  readonly direction: 'ascending' | 'descending';
}

export type Total =
  | {
      readonly kind: 'sum';
      readonly sum: number;
      readonly unit: string;
      readonly provenance: Provenance;
    }
  | { readonly kind: 'none'; readonly why: string };

/**
 * A column's total, or why it has none. Only figures of one unit and one provenance add up:
 * dollars and euros do not, a measured cost and a modelled saving do not, and a figure that
 * was not collected is not a zero, so a column holding one has no total rather than a total
 * that is too small and looks complete.
 */
export function columnTotal<Row>(rows: readonly Row[], total: ColumnTotal<Row>): Total {
  if (rows.length === 0) {
    return { kind: 'none', why: 'No total: nothing to add up' };
  }
  const values = rows.map(total.value);
  if (values.some((value) => value === null)) {
    return { kind: 'none', why: 'No total: a figure was not collected' };
  }
  const units = [...new Set(rows.map(total.unit))];
  if (units.length > 1) {
    return { kind: 'none', why: 'No total: more than one unit' };
  }
  const provenances = [...new Set(rows.map(total.provenance))].sort();
  if (provenances.length > 1) {
    return { kind: 'none', why: `No total: ${provenances.join(' and ')} figures mixed` };
  }
  return {
    kind: 'sum',
    sum: values.reduce<number>((sum, value) => sum + (value ?? 0), 0),
    unit: units[0] ?? '',
    provenance: provenances[0] ?? 'measured',
  };
}

/** The next sort after a click on `column`: a figure first sorts largest first. */
export function nextSort<Row>(current: Sort | null, column: Column<Row>): Sort {
  if (current?.key === column.key) {
    return {
      key: column.key,
      direction: current.direction === 'ascending' ? 'descending' : 'ascending',
    };
  }
  return { key: column.key, direction: column.numeric === true ? 'descending' : 'ascending' };
}

/** The rows in `sort` order, as a new array. A null sorts last in either direction. */
export function sortRows<Row>(
  rows: readonly Row[],
  columns: readonly Column<Row>[],
  sort: Sort,
): readonly Row[] {
  const by = columns.find((column) => column.key === sort.key)?.sortValue;
  if (by === undefined) {
    return rows;
  }
  const sign = sort.direction === 'ascending' ? 1 : -1;
  return [...rows].sort((left, right) => {
    const a = by(left);
    const b = by(right);
    if (a === null || b === null) {
      return a === b ? 0 : a === null ? 1 : -1;
    }
    const order =
      typeof a === 'number' && typeof b === 'number'
        ? a - b
        : String(a).localeCompare(String(b), 'en-GB', { numeric: true });
    return order * sign;
  });
}
