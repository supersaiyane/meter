import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import layout from '../../layout.css?raw';
import { DataTable } from '../DataTable';
import type { Column, Sort } from '../tableConfig';

/** TASK-P8-006: tables that sort and total, and a reader chooses the columns. */

interface Line {
  readonly name: string;
  readonly cost: number | null;
  readonly unit: string;
  readonly kind: 'measured' | 'modelled';
}

const LINES: readonly Line[] = [
  { name: 'b', cost: 2, unit: 'USD', kind: 'measured' },
  { name: 'a', cost: 10, unit: 'USD', kind: 'measured' },
  { name: 'c', cost: 5, unit: 'USD', kind: 'measured' },
];

const COLUMNS: readonly Column<Line>[] = [
  { key: 'name', header: 'Name', render: (row) => row.name, sortValue: (row) => row.name },
  {
    key: 'cost',
    header: 'Cost',
    numeric: true,
    render: (row) => (row.cost === null ? 'not collected' : String(row.cost)),
    sortValue: (row) => row.cost,
    total: {
      value: (row) => row.cost,
      unit: (row) => row.unit,
      provenance: (row) => row.kind,
      render: (sum) => `total ${String(sum)}`,
    },
  },
];

function table(lines: readonly Line[] = LINES, initialSort?: Sort): ReturnType<typeof render> {
  return render(
    <DataTable
      rows={lines}
      columns={COLUMNS}
      rowKey={(row) => row.name}
      caption="Lines"
      {...(initialSort === undefined ? {} : { initialSort })}
    />,
  );
}

const names = (): (string | null | undefined)[] =>
  [...document.querySelectorAll('tbody tr')].map((row) => row.querySelector('td')?.textContent);

describe('DataTable, sorting', () => {
  it('sorts a figure largest first, then the other way, and says so with aria-sort', async () => {
    const user = userEvent.setup();
    table();
    const cost = screen.getByRole('columnheader', { name: /Cost/ });
    expect(cost).toHaveAttribute('aria-sort', 'none');
    await user.click(within(cost).getByRole('button'));
    expect(cost).toHaveAttribute('aria-sort', 'descending');
    expect(names()).toEqual(['a', 'c', 'b']);
    await user.click(within(cost).getByRole('button'));
    expect(cost).toHaveAttribute('aria-sort', 'ascending');
    expect(names()).toEqual(['b', 'c', 'a']);
  });

  it('sorts by keyboard as well as by pointer', async () => {
    const user = userEvent.setup();
    table();
    within(screen.getByRole('columnheader', { name: /Name/ }))
      .getByRole('button')
      .focus();
    await user.keyboard('{Enter}');
    expect(names()).toEqual(['a', 'b', 'c']);
  });

  it('puts a figure that was not collected last, whichever way it sorts', async () => {
    const user = userEvent.setup();
    table([...LINES, { name: 'd', cost: null, unit: 'USD', kind: 'measured' }]);
    const sort = within(screen.getByRole('columnheader', { name: /Cost/ })).getByRole('button');
    await user.click(sort);
    expect(names().at(-1)).toBe('d');
    await user.click(sort);
    expect(names().at(-1)).toBe('d');
  });
});

describe('DataTable, totals', () => {
  it('totals a column of one unit and one provenance', () => {
    table();
    expect(screen.getByTestId('total-cost')).toHaveTextContent('total 17');
  });

  it('says why a column mixing units has no total', () => {
    table([...LINES, { name: 'd', cost: 3, unit: 'EUR', kind: 'measured' }]);
    expect(screen.getByTestId('total-cost')).toHaveTextContent('No total: more than one unit');
  });

  it('says why a column mixing measured and modelled has no total', () => {
    table([...LINES, { name: 'd', cost: 3, unit: 'USD', kind: 'modelled' }]);
    expect(screen.getByTestId('total-cost')).toHaveTextContent(
      'No total: measured and modelled figures mixed',
    );
  });

  it('gives no total when a figure was not collected, rather than adding it as zero', () => {
    table([...LINES, { name: 'd', cost: null, unit: 'USD', kind: 'measured' }]);
    expect(screen.getByTestId('total-cost')).toHaveTextContent(
      'No total: a figure was not collected',
    );
  });

  it('says there is nothing to add up when there are no rows', () => {
    table([]);
    expect(screen.getByTestId('total-cost')).toHaveTextContent('No total: nothing to add up');
  });

  it('labels the totals row in the first column when that column has no total of its own', () => {
    table();
    expect(screen.getByTestId('total-name')).toHaveTextContent('Total');
  });
});

describe('DataTable, columns and rows', () => {
  it('hides a column a reader chooses to hide', async () => {
    const user = userEvent.setup();
    table();
    await user.click(screen.getByText('Columns'));
    await user.click(screen.getByRole('checkbox', { name: 'Cost' }));
    expect(screen.queryByRole('columnheader', { name: /Cost/ })).toBeNull();
  });

  it('says the order rows arrive in from the first render, so a caption need not', () => {
    table(LINES, { key: 'cost', direction: 'descending' });
    expect(screen.getByRole('columnheader', { name: /Cost/ })).toHaveAttribute(
      'aria-sort',
      'descending',
    );
    expect(screen.getByRole('columnheader', { name: /Name/ })).toHaveAttribute(
      'aria-sort',
      'none',
    );
    expect(names()).toEqual(['a', 'c', 'b']);
  });

  it('leaves a column that does not sort without aria-sort or a button', () => {
    render(
      <DataTable
        rows={LINES}
        columns={[{ key: 'name', header: 'Name', render: (row: Line) => row.name }]}
        rowKey={(row) => row.name}
        caption="Lines"
      />,
    );
    const header = screen.getByRole('columnheader', { name: 'Name' });
    expect(header).not.toHaveAttribute('aria-sort');
    expect(within(header).queryByRole('button')).toBeNull();
    expect(screen.queryByTestId('totals-row')).toBeNull();
  });

  it('shows a hidden column again, and never lets the last column go', async () => {
    const user = userEvent.setup();
    table();
    await user.click(screen.getByText('Columns'));
    await user.click(screen.getByRole('checkbox', { name: 'Cost' }));
    expect(screen.getByRole('checkbox', { name: 'Name' })).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: 'Cost' }));
    expect(screen.getByRole('columnheader', { name: /Cost/ })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Name' })).toBeEnabled();
  });

  it('leaves the order alone when the sort names a column that does not sort', () => {
    table(LINES, { key: 'nothing', direction: 'ascending' });
    expect(names()).toEqual(['b', 'a', 'c']);
  });

  it('keeps the header in view while the rows scroll', () => {
    expect(layout).toMatch(/^thead th \{[^}]*position: sticky/m);
  });
});
