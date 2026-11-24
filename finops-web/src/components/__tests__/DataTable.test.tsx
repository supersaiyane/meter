import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DataTable } from '../DataTable';
import { VIRTUALISE_ABOVE, type Column } from '../tableConfig';
import { violationsIn } from './axe';

interface Row {
  readonly id: string;
  readonly name: string;
}

const COLUMNS: readonly Column<Row>[] = [
  { key: 'name', header: 'Account', render: (row) => row.name },
];

function rows(count: number): Row[] {
  return Array.from({ length: count }, (_, index) => ({
    id: String(index),
    name: `account-${String(index)}`,
  }));
}

describe('DataTable', () => {
  it('renders every row below the threshold', () => {
    render(
      <DataTable
        rows={rows(VIRTUALISE_ABOVE)}
        columns={COLUMNS}
        rowKey={(row) => row.id}
        caption="Accounts"
      />,
    );
    expect(screen.getByTestId('table').dataset['virtualised']).toBe('false');
    expect(screen.getAllByRole('row')).toHaveLength(VIRTUALISE_ABOVE + 1);
  });

  it('virtualises past two hundred rows', () => {
    const count = VIRTUALISE_ABOVE + 100;
    render(
      <DataTable
        rows={rows(count)}
        columns={COLUMNS}
        rowKey={(row) => row.id}
        caption="Accounts"
      />,
    );
    expect(screen.getByTestId('table').dataset['virtualised']).toBe('true');
    // The point is that the document does not hold every row. How many it holds
    // depends on the viewport, which is why the assertion is on the property and
    // not on a count.
    expect(screen.queryAllByRole('row').length).toBeLessThan(count + 1);
  });

  it('marks numeric columns tabular so a column aligns by digit', () => {
    const numeric: readonly Column<Row>[] = [
      { key: 'name', header: 'Account', render: (row) => row.name, numeric: true },
    ];
    const { container } = render(
      <DataTable
        rows={rows(2)}
        columns={numeric}
        rowKey={(row) => row.id}
        caption="Accounts"
      />,
    );
    expect(container.querySelector('td')?.className).toContain('meter-numeral');
  });

  it('carries a caption, so the table has a name', async () => {
    const { container } = render(
      <DataTable
        rows={rows(3)}
        columns={COLUMNS}
        rowKey={(row) => row.id}
        caption="Accounts"
      />,
    );
    expect(screen.getByText('Accounts')).toBeInTheDocument();
    expect(await violationsIn(container)).toEqual([]);
  });
});
