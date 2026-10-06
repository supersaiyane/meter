import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

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

describe('DataTable, a table wider than its box', () => {
  // jsdom lays nothing out, so the box's sizes are given here and the observer is a stub that
  // reports the sizes once, as a browser's does when it starts observing.
  function sized(scrollWidth: number, clientWidth: number): void {
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe(): void {}
        disconnect(): void {}
      },
    );
    Object.defineProperty(HTMLElement.prototype, 'scrollWidth', {
      configurable: true,
      get: () => scrollWidth,
    });
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
      configurable: true,
      get: () => clientWidth,
    });
  }

  afterEach(() => {
    vi.unstubAllGlobals();
    delete (HTMLElement.prototype as { scrollWidth?: number }).scrollWidth;
    delete (HTMLElement.prototype as { clientWidth?: number }).clientWidth;
  });

  it('is a keyboard stop named by its caption while it scrolls, so its last columns are reachable', () => {
    sized(900, 300);
    render(
      <DataTable rows={rows(3)} columns={COLUMNS} rowKey={(row) => row.id} caption="Wide" />,
    );
    const box = screen.getByTestId('table-scroll');
    expect(box).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('region', { name: 'Wide' })).toBe(box);
  });

  it('adds nothing to the tab order when the table fits', () => {
    sized(300, 300);
    render(
      <DataTable rows={rows(3)} columns={COLUMNS} rowKey={(row) => row.id} caption="Fits" />,
    );
    expect(screen.getByTestId('table-scroll')).not.toHaveAttribute('tabindex');
    expect(screen.queryByRole('region')).toBeNull();
  });
});

describe("DataTable, the hooks a screen's own table carried", () => {
  it("puts a screen's row attributes on each row and a column's test id on each cell", () => {
    render(
      <DataTable
        rows={rows(2)}
        columns={COLUMNS.map((column) => ({ ...column, cellTestId: 'account-cell' }))}
        rowKey={(row) => row.id}
        caption="Hooked"
        rowAttributes={(row) => ({ 'data-testid': 'account-row', 'data-id': row.id })}
      />,
    );
    const found = screen.getAllByTestId('account-row');
    expect(found.map((row) => row.getAttribute('data-id'))).toEqual(['0', '1']);
    expect(screen.getAllByTestId('account-cell').map((cell) => cell.textContent)).toEqual([
      'account-0',
      'account-1',
    ]);
  });
});
