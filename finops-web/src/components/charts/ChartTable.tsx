/**
 * The numbers behind a chart, as a table a keyboard and a screen reader can use, P8 spec
 * section 5.4. Behind a disclosure so the picture leads, and in the page so nothing has to
 * be fetched to read it. Each cell carries its value, which is what the tests hold equal to
 * the marks the chart drew.
 */

export interface TableCell {
  /** Null for a cell that states no number: a share, a gap, a figure not collected. */
  readonly value: number | null;
  readonly text: string;
}

export interface TableRow {
  readonly label: string;
  readonly cells: readonly TableCell[];
}

export interface ChartTableProps {
  readonly caption: string;
  /** What the first column names: a series, a category, a period. */
  readonly rowHeader: string;
  readonly columns: readonly string[];
  readonly rows: readonly TableRow[];
}

export function ChartTable({ caption, rowHeader, columns, rows }: ChartTableProps) {
  return (
    <details data-testid="chart-table">
      <summary>Show the numbers</summary>
      <table>
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th scope="col">{rowHeader}</th>
            {columns.map((column) => (
              <th key={column} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <th scope="row">{row.label}</th>
              {row.cells.map((cell, index) => (
                <td key={columns[index] ?? String(index)} data-value={cell.value ?? ''}>
                  {cell.text}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
